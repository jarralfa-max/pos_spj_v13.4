"""Use cases de recetas (capa de aplicación sobre el dominio existente).

Orquesta el ciclo de vida versionado de recetas: crear (receta + versión v1 DRAFT),
editar la versión mientras es editable, y las transiciones enviar→aprobar→activar.
Cada mutación exige el permiso granular correspondiente (fail-closed); aprobar y
activar aplican **segregación de funciones** (quien creó la versión no puede
aprobarla/activarla). La validación de dominio (componentes/outputs, ciclos) corre
en ``RecipeValidationService``. El caso de uso es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
    UpdateDraftVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.recipe import Recipe
from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.recipe_enums import RecipeVersionStatus
from backend.domain.products.services.recipe_validation_service import (
    RecipeValidationService,
)
from backend.infrastructure.db.repositories.products.recipe_repository import (
    RecipeRepository,
)

logger = logging.getLogger("spj.products.recipe_use_cases")


@dataclass(frozen=True)
class RecipeResult:
    success: bool
    recipe_id: str | None
    version_id: str | None
    message: str


def _components(rows: list[dict]) -> list[RecipeComponent]:
    return [RecipeComponent(
        component_product_id=r["component_product_id"], quantity=r["quantity"],
        unit_id=r["unit_id"], scrap_pct=r.get("scrap_pct", 0),
        sequence=int(r.get("sequence", i)))
        for i, r in enumerate(rows)]


def _outputs(rows: list[dict]) -> list[RecipeOutput]:
    return [RecipeOutput(
        product_id=r["product_id"], output_type=r["output_type"],
        quantity=r["quantity"], unit_id=r["unit_id"],
        expected_yield_pct=r.get("expected_yield_pct"),
        sequence=int(r.get("sequence", i)))
        for i, r in enumerate(rows)]


class _BaseRecipeUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = RecipeRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        self._validator = RecipeValidationService()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _persist(self, version, event_name, command, message) -> "RecipeResult":
        """Guarda la versión, emite el evento y confirma la transacción."""
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action=message, entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"status": version.status.value, "recipe_id": version.recipe_id})
            _emit(self._conn, event_name, command, entity_id=version.id,
                  extra={"recipe_id": version.recipe_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("persist recipe version failed op=%s",
                             command.operation_id)
            raise
        return RecipeResult(True, version.recipe_id, version.id, message)


class CreateProductRecipeUseCase(_BaseRecipeUseCase):
    name = "CreateProductRecipeUseCase"

    def execute(self, command: CreateRecipeCommand) -> RecipeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.RECIPE_CREATE)
        try:
            recipe = Recipe(product_id=command.product_id,
                            recipe_type=command.recipe_type, name=command.name)
            version = RecipeVersion(
                recipe_id=recipe.id, version_number=1,
                status=RecipeVersionStatus.DRAFT,
                components=_components(command.components),
                outputs=_outputs(command.outputs), created_by=command.user_id)
            self._validator.validate(recipe, version,
                                     resolver=self._repo.component_resolver())
        except ProductsDomainError as exc:
            return RecipeResult(False, None, None, str(exc))
        try:
            self._repo.save_recipe(recipe)
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="PRODUCT_RECIPE_CREATED", entity_id=recipe.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"product_id": recipe.product_id, "version_id": version.id})
            _emit(self._conn, ProductEvents.PRODUCT_RECIPE_CREATED, command,
                  entity_id=recipe.id, extra={"product_id": recipe.product_id,
                                              "version_id": version.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create recipe failed op=%s", command.operation_id)
            raise
        return RecipeResult(True, recipe.id, version.id, "PRODUCT_RECIPE_CREATED")


class UpdateDraftVersionUseCase(_BaseRecipeUseCase):
    name = "UpdateDraftVersionUseCase"

    def execute(self, command: UpdateDraftVersionCommand) -> RecipeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.RECIPE_EDIT)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return RecipeResult(False, None, None, "La versión no existe")
        recipe = self._repo.get_recipe(version.recipe_id)
        if recipe is None:
            return RecipeResult(False, None, None, "La receta no existe")
        if not version.is_editable:
            return RecipeResult(False, recipe.id, version.id,
                                "La versión ya no es editable (aprobada/activa)")
        try:
            version.components = _components(command.components)
            version.outputs = _outputs(command.outputs)
            self._validator.validate(recipe, version,
                                     resolver=self._repo.component_resolver())
        except ProductsDomainError as exc:
            return RecipeResult(False, recipe.id, version.id, str(exc))
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="RECIPE_VERSION_UPDATED", entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"recipe_id": recipe.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update draft version failed op=%s", command.operation_id)
            raise
        return RecipeResult(True, recipe.id, version.id, "RECIPE_VERSION_UPDATED")


class SubmitRecipeVersionUseCase(_BaseRecipeUseCase):
    name = "SubmitRecipeVersionUseCase"

    def execute(self, command: RecipeVersionTransitionCommand) -> RecipeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.RECIPE_EDIT)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return RecipeResult(False, None, None, "La versión no existe")
        try:
            version.submit()
        except ProductsDomainError as exc:
            return RecipeResult(False, version.recipe_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_RECIPE_VERSION_CREATED,
                             command, "RECIPE_VERSION_SUBMITTED")


class ApproveRecipeVersionUseCase(_BaseRecipeUseCase):
    name = "ApproveRecipeVersionUseCase"

    def execute(self, command: RecipeVersionTransitionCommand) -> RecipeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.RECIPE_APPROVE)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return RecipeResult(False, None, None, "La versión no existe")
        # §39 segregación: quien creó la versión no puede aprobarla.
        self._auth.ensure_segregation(
            actor_user_id=command.user_id or "", creator_user_id=version.created_by,
            approval_permission=ProductPermissions.RECIPE_APPROVE)
        try:
            version.approve(approved_by_user_id=command.user_id or "",
                            reason=command.reason)
        except ProductsDomainError as exc:
            return RecipeResult(False, version.recipe_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_RECIPE_VERSION_APPROVED,
                             command, "RECIPE_VERSION_APPROVED")


class ActivateRecipeVersionUseCase(_BaseRecipeUseCase):
    name = "ActivateRecipeVersionUseCase"

    def execute(self, command: RecipeVersionTransitionCommand) -> RecipeResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.RECIPE_ACTIVATE)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return RecipeResult(False, None, None, "La versión no existe")
        self._auth.ensure_segregation(
            actor_user_id=command.user_id or "", creator_user_id=version.created_by,
            approval_permission=ProductPermissions.RECIPE_ACTIVATE)
        current = self._repo.active_version_for_recipe(version.recipe_id)
        try:
            version.activate()
            if current is not None and current.id != version.id:
                current.supersede()
        except ProductsDomainError as exc:
            return RecipeResult(False, version.recipe_id, version.id, str(exc))
        try:
            if current is not None and current.id != version.id:
                self._repo.save_version(current)  # supersede el activo anterior
            self._repo.save_version(version)
            _emit(self._conn, ProductEvents.PRODUCT_RECIPE_VERSION_ACTIVATED, command,
                  entity_id=version.id, extra={"recipe_id": version.recipe_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("activate recipe version failed op=%s",
                             command.operation_id)
            raise
        return RecipeResult(True, version.recipe_id, version.id,
                            "RECIPE_VERSION_ACTIVATED")


def _emit(conn, event_name: str, command, *, entity_id: str, extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
               "operation_id": command.operation_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, entity_id,
         json.dumps(payload)))
