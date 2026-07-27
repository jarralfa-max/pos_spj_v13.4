"""Use cases de combos/kits (§28) — capa de aplicación sobre el dominio existente.

Ciclo de vida versionado: crear (combo + versión v1 DRAFT con componentes), editar la
versión mientras es editable, y enviar→aprobar→activar. Toda mutación exige
``PRODUCTS_BUNDLES_MANAGE`` (fail-closed). Validación de dominio (componentes,
duplicados, ciclos directo/transitivo) en ``BundleExplosionService``. Activar
reemplaza (SUPERSEDED) la versión activa anterior. El caso de uso es dueño de la tx.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_bundle_commands import (
    BundleVersionTransitionCommand,
    CreateBundleCommand,
    UpdateBundleVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.bundle_component import BundleComponent
from backend.domain.products.entities.bundle_version import BundleVersion
from backend.domain.products.entities.product_bundle import ProductBundle
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.recipe_enums import RecipeVersionStatus
from backend.domain.products.services.bundle_explosion_service import (
    BundleExplosionService,
)
from backend.infrastructure.db.repositories.products.bundle_repository import (
    BundleRepository,
)

logger = logging.getLogger("spj.products.bundle_use_cases")


@dataclass(frozen=True)
class BundleResult:
    success: bool
    bundle_id: str | None
    version_id: str | None
    message: str


def _components(rows: list[dict]) -> list[BundleComponent]:
    return [BundleComponent(
        component_product_id=r["component_product_id"], quantity=r["quantity"],
        unit_id=r["unit_id"], optional=bool(r.get("optional", False)),
        substitutable=bool(r.get("substitutable", False)),
        sequence=int(r.get("sequence", i)))
        for i, r in enumerate(rows)]


class _BaseBundleUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = BundleRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy()
        self._validator = BundleExplosionService()

    def _require(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.BUNDLES_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _persist(self, version, event_name, command, message) -> BundleResult:
        try:
            self._repo.save_version(version)
            _emit(self._conn, event_name, command, entity_id=version.id,
                  extra={"bundle_id": version.bundle_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("persist bundle version failed op=%s",
                             command.operation_id)
            raise
        return BundleResult(True, version.bundle_id, version.id, message)


class CreateProductBundleUseCase(_BaseBundleUseCase):
    name = "CreateProductBundleUseCase"

    def execute(self, command: CreateBundleCommand) -> BundleResult:
        command.validate()
        self._require(command.user_id)
        try:
            bundle = ProductBundle(product_id=command.product_id,
                                   bundle_type=command.bundle_type, name=command.name)
            version = BundleVersion(
                bundle_id=bundle.id, version_number=1,
                status=RecipeVersionStatus.DRAFT,
                components=_components(command.components))
            self._validator.validate(bundle, version,
                                     resolver=self._repo.component_resolver())
        except ProductsDomainError as exc:
            return BundleResult(False, None, None, str(exc))
        try:
            self._repo.save_bundle(bundle)
            self._repo.save_version(version)
            _emit(self._conn, ProductEvents.PRODUCT_BUNDLE_CREATED, command,
                  entity_id=bundle.id,
                  extra={"product_id": bundle.product_id, "version_id": version.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create bundle failed op=%s", command.operation_id)
            raise
        return BundleResult(True, bundle.id, version.id, "PRODUCT_BUNDLE_CREATED")


class UpdateBundleVersionUseCase(_BaseBundleUseCase):
    name = "UpdateBundleVersionUseCase"

    def execute(self, command: UpdateBundleVersionCommand) -> BundleResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return BundleResult(False, None, None, "La versión no existe")
        bundle = self._repo.get_bundle(version.bundle_id)
        if bundle is None:
            return BundleResult(False, None, None, "El combo no existe")
        if not version.is_editable:
            return BundleResult(False, bundle.id, version.id,
                                "La versión ya no es editable (aprobada/activa)")
        try:
            version.components = _components(command.components)
            self._validator.validate(bundle, version,
                                     resolver=self._repo.component_resolver())
        except ProductsDomainError as exc:
            return BundleResult(False, bundle.id, version.id, str(exc))
        try:
            self._repo.save_version(version)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update bundle version failed op=%s",
                             command.operation_id)
            raise
        return BundleResult(True, bundle.id, version.id, "BUNDLE_VERSION_UPDATED")


class SubmitBundleVersionUseCase(_BaseBundleUseCase):
    name = "SubmitBundleVersionUseCase"

    def execute(self, command: BundleVersionTransitionCommand) -> BundleResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return BundleResult(False, None, None, "La versión no existe")
        try:
            version.submit()
        except ProductsDomainError as exc:
            return BundleResult(False, version.bundle_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_BUNDLE_CREATED,
                             command, "BUNDLE_VERSION_SUBMITTED")


class ApproveBundleVersionUseCase(_BaseBundleUseCase):
    name = "ApproveBundleVersionUseCase"

    def execute(self, command: BundleVersionTransitionCommand) -> BundleResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return BundleResult(False, None, None, "La versión no existe")
        try:
            version.approve(approved_by_user_id=command.user_id or "",
                            reason=command.reason)
        except ProductsDomainError as exc:
            return BundleResult(False, version.bundle_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_BUNDLE_CREATED,
                             command, "BUNDLE_VERSION_APPROVED")


class ActivateBundleVersionUseCase(_BaseBundleUseCase):
    name = "ActivateBundleVersionUseCase"

    def execute(self, command: BundleVersionTransitionCommand) -> BundleResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return BundleResult(False, None, None, "La versión no existe")
        current = self._repo.active_version_for_bundle(version.bundle_id)
        try:
            version.activate()
            if current is not None and current.id != version.id:
                current.supersede()
        except ProductsDomainError as exc:
            return BundleResult(False, version.bundle_id, version.id, str(exc))
        try:
            if current is not None and current.id != version.id:
                self._repo.save_version(current)
            self._repo.save_version(version)
            _emit(self._conn, ProductEvents.PRODUCT_BUNDLE_VERSION_ACTIVATED, command,
                  entity_id=version.id, extra={"bundle_id": version.bundle_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("activate bundle version failed op=%s",
                             command.operation_id)
            raise
        return BundleResult(True, version.bundle_id, version.id,
                            "BUNDLE_VERSION_ACTIVATED")


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
