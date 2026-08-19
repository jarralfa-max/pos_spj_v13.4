"""Use cases de rendimientos (yields) — capa de aplicación sobre el dominio.

Ciclo de vida versionado de perfiles de rendimiento: crear (perfil + versión v1
DRAFT con outputs), editar la versión mientras es editable, y enviar→aprobar→activar.
Cada mutación exige el permiso YIELD_* correspondiente (fail-closed); aprobar/activar
aplican segregación de funciones (quien creó la versión no puede aprobarla/activarla)
y activar reemplaza (SUPERSEDED) la versión activa anterior. Validación de dominio en
``YieldValidationService``. El caso de uso es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_yield_commands import (
    CreateYieldProfileCommand,
    UpdateYieldVersionCommand,
    YieldVersionTransitionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.yield_output import YieldOutput
from backend.domain.products.entities.yield_profile import YieldProfile
from backend.domain.products.entities.yield_profile_version import YieldProfileVersion
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.recipe_enums import RecipeVersionStatus
from backend.domain.products.services.yield_validation_service import (
    YieldValidationService,
)
from backend.infrastructure.db.repositories.products.yield_repository import (
    YieldRepository,
)

logger = logging.getLogger("spj.products.yield_use_cases")


@dataclass(frozen=True)
class YieldResult:
    success: bool
    profile_id: str | None
    version_id: str | None
    message: str


def _outputs(rows: list[dict]) -> list[YieldOutput]:
    return [YieldOutput(
        product_id=r["product_id"], output_type=r["output_type"],
        expected_yield_pct=r["expected_yield_pct"], unit_id=r["unit_id"],
        expected_quantity=r.get("expected_quantity", 0),
        minimum_yield_pct=r.get("minimum_yield_pct"),
        maximum_yield_pct=r.get("maximum_yield_pct"),
        cost_allocation_weight=r.get("cost_allocation_weight", 0),
        sequence=int(r.get("sequence", i)))
        for i, r in enumerate(rows)]


class _BaseYieldUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = YieldRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        self._validator = YieldValidationService()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _persist(self, version, event_name, command, message) -> YieldResult:
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action=message, entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"status": version.status.value,
                       "profile_id": version.yield_profile_id})
            _emit(self._conn, event_name, command, entity_id=version.id,
                  extra={"profile_id": version.yield_profile_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("persist yield version failed op=%s",
                             command.operation_id)
            raise
        return YieldResult(True, version.yield_profile_id, version.id, message)


class CreateYieldProfileUseCase(_BaseYieldUseCase):
    name = "CreateYieldProfileUseCase"

    def execute(self, command: CreateYieldProfileCommand) -> YieldResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.YIELD_CREATE)
        try:
            profile = YieldProfile(input_product_id=command.input_product_id,
                                   name=command.name, species_id=command.species_id)
            version = YieldProfileVersion(
                yield_profile_id=profile.id, version_number=1,
                status=RecipeVersionStatus.DRAFT, tolerance_pct=command.tolerance_pct,
                outputs=_outputs(command.outputs), created_by=command.user_id)
            self._validator.validate(version)
        except ProductsDomainError as exc:
            return YieldResult(False, None, None, str(exc))
        try:
            self._repo.save_profile(profile)
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="PRODUCT_YIELD_PROFILE_CREATED", entity_id=profile.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"input_product_id": profile.input_product_id,
                       "version_id": version.id})
            _emit(self._conn, ProductEvents.PRODUCT_YIELD_PROFILE_CREATED, command,
                  entity_id=profile.id,
                  extra={"input_product_id": profile.input_product_id,
                         "version_id": version.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create yield profile failed op=%s", command.operation_id)
            raise
        return YieldResult(True, profile.id, version.id, "PRODUCT_YIELD_PROFILE_CREATED")


class UpdateYieldVersionUseCase(_BaseYieldUseCase):
    name = "UpdateYieldVersionUseCase"

    def execute(self, command: UpdateYieldVersionCommand) -> YieldResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.YIELD_EDIT)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return YieldResult(False, None, None, "La versión no existe")
        if not version.is_editable:
            return YieldResult(False, version.yield_profile_id, version.id,
                               "La versión ya no es editable (aprobada/activa)")
        try:
            from decimal import Decimal
            version.tolerance_pct = Decimal(str(command.tolerance_pct))
            version.outputs = _outputs(command.outputs)
            self._validator.validate(version)
        except ProductsDomainError as exc:
            return YieldResult(False, version.yield_profile_id, version.id, str(exc))
        except Exception as exc:  # Decimal inválido u otros
            return YieldResult(False, version.yield_profile_id, version.id, str(exc))
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="YIELD_VERSION_UPDATED", entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"profile_id": version.yield_profile_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update yield version failed op=%s", command.operation_id)
            raise
        return YieldResult(True, version.yield_profile_id, version.id,
                           "YIELD_VERSION_UPDATED")


class SubmitYieldVersionUseCase(_BaseYieldUseCase):
    name = "SubmitYieldVersionUseCase"

    def execute(self, command: YieldVersionTransitionCommand) -> YieldResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.YIELD_EDIT)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return YieldResult(False, None, None, "La versión no existe")
        try:
            version.submit()
        except ProductsDomainError as exc:
            return YieldResult(False, version.yield_profile_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_YIELD_PROFILE_CREATED,
                             command, "YIELD_VERSION_SUBMITTED")


class ApproveYieldVersionUseCase(_BaseYieldUseCase):
    name = "ApproveYieldVersionUseCase"

    def execute(self, command: YieldVersionTransitionCommand) -> YieldResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.YIELD_APPROVE)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return YieldResult(False, None, None, "La versión no existe")
        self._auth.ensure_segregation(
            actor_user_id=command.user_id or "", creator_user_id=version.created_by,
            approval_permission=ProductPermissions.YIELD_APPROVE)
        try:
            version.approve(approved_by_user_id=command.user_id or "",
                            reason=command.reason)
        except ProductsDomainError as exc:
            return YieldResult(False, version.yield_profile_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_YIELD_VERSION_APPROVED,
                             command, "YIELD_VERSION_APPROVED")


class ActivateYieldVersionUseCase(_BaseYieldUseCase):
    name = "ActivateYieldVersionUseCase"

    def execute(self, command: YieldVersionTransitionCommand) -> YieldResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.YIELD_ACTIVATE)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return YieldResult(False, None, None, "La versión no existe")
        self._auth.ensure_segregation(
            actor_user_id=command.user_id or "", creator_user_id=version.created_by,
            approval_permission=ProductPermissions.YIELD_ACTIVATE)
        current = self._repo.active_version_for_profile(version.yield_profile_id)
        try:
            version.activate()
            if current is not None and current.id != version.id:
                current.supersede()
        except ProductsDomainError as exc:
            return YieldResult(False, version.yield_profile_id, version.id, str(exc))
        try:
            if current is not None and current.id != version.id:
                self._repo.save_version(current)
            self._repo.save_version(version)
            _emit(self._conn, ProductEvents.PRODUCT_YIELD_VERSION_ACTIVATED, command,
                  entity_id=version.id,
                  extra={"profile_id": version.yield_profile_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("activate yield version failed op=%s",
                             command.operation_id)
            raise
        return YieldResult(True, version.yield_profile_id, version.id,
                           "YIELD_VERSION_ACTIVATED")


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
