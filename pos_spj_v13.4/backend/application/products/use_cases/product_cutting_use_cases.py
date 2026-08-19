"""Use cases de esquemas de despiece (cutting) — capa de aplicación.

Ciclo de vida versionado: crear (esquema + versión v1 DRAFT con outputs), editar la
versión mientras es editable, y enviar→aprobar→activar. Toda mutación exige
``PRODUCTS_CUTTING_SCHEME_MANAGE`` (fail-closed). Validación de dominio (outputs,
producto duplicado, auto-contención) en ``CuttingSchemeService``. Activar reemplaza
(SUPERSEDED) la versión activa anterior. El caso de uso es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_cutting_commands import (
    CreateCuttingSchemeCommand,
    CuttingVersionTransitionCommand,
    UpdateCuttingVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.cutting_output import CuttingOutput
from backend.domain.products.entities.cutting_scheme import CuttingScheme
from backend.domain.products.entities.cutting_scheme_version import CuttingSchemeVersion
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.recipe_enums import RecipeVersionStatus
from backend.domain.products.services.cutting_scheme_service import (
    CuttingSchemeService,
)
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)

logger = logging.getLogger("spj.products.cutting_use_cases")


@dataclass(frozen=True)
class CuttingResult:
    success: bool
    scheme_id: str | None
    version_id: str | None
    message: str


def _outputs(rows: list[dict]) -> list[CuttingOutput]:
    return [CuttingOutput(
        product_id=r["product_id"], measure_kind=r.get("measure_kind", "BY_WEIGHT"),
        quantity=r["quantity"], unit_id=r["unit_id"],
        output_type=r.get("output_type", "MAIN_PRODUCT"),
        cut_level=r.get("cut_level"), sequence=int(r.get("sequence", i)))
        for i, r in enumerate(rows)]


class _BaseCuttingUseCase:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = CuttingSchemeRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()
        self._validator = CuttingSchemeService()

    def _require(self, user_id: str | None) -> None:
        self._auth.require(user_id or "", ProductPermissions.CUTTING_SCHEME_MANAGE)

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()

    def _persist(self, version, event_name, command, message) -> CuttingResult:
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action=message, entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"status": version.status.value,
                       "scheme_id": version.cutting_scheme_id})
            _emit(self._conn, event_name, command, entity_id=version.id,
                  extra={"scheme_id": version.cutting_scheme_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("persist cutting version failed op=%s",
                             command.operation_id)
            raise
        return CuttingResult(True, version.cutting_scheme_id, version.id, message)


class CreateCuttingSchemeUseCase(_BaseCuttingUseCase):
    name = "CreateCuttingSchemeUseCase"

    def execute(self, command: CreateCuttingSchemeCommand) -> CuttingResult:
        command.validate()
        self._require(command.user_id)
        try:
            scheme = CuttingScheme(input_product_id=command.input_product_id,
                                   species_id=command.species_id, name=command.name,
                                   cut_level=command.cut_level)
            version = CuttingSchemeVersion(
                cutting_scheme_id=scheme.id, version_number=1,
                status=RecipeVersionStatus.DRAFT, outputs=_outputs(command.outputs))
            self._validator.validate(scheme, version)
        except ProductsDomainError as exc:
            return CuttingResult(False, None, None, str(exc))
        try:
            self._repo.save_scheme(scheme)
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="PRODUCT_CUTTING_SCHEME_CREATED", entity_id=scheme.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"input_product_id": scheme.input_product_id,
                       "version_id": version.id})
            _emit(self._conn, ProductEvents.PRODUCT_CUTTING_SCHEME_CREATED, command,
                  entity_id=scheme.id,
                  extra={"input_product_id": scheme.input_product_id,
                         "version_id": version.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create cutting scheme failed op=%s", command.operation_id)
            raise
        return CuttingResult(True, scheme.id, version.id,
                             "PRODUCT_CUTTING_SCHEME_CREATED")


class UpdateCuttingVersionUseCase(_BaseCuttingUseCase):
    name = "UpdateCuttingVersionUseCase"

    def execute(self, command: UpdateCuttingVersionCommand) -> CuttingResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return CuttingResult(False, None, None, "La versión no existe")
        scheme = self._repo.get_scheme(version.cutting_scheme_id)
        if scheme is None:
            return CuttingResult(False, None, None, "El esquema no existe")
        if not version.is_editable:
            return CuttingResult(False, scheme.id, version.id,
                                 "La versión ya no es editable (aprobada/activa)")
        try:
            version.outputs = _outputs(command.outputs)
            self._validator.validate(scheme, version)
        except ProductsDomainError as exc:
            return CuttingResult(False, scheme.id, version.id, str(exc))
        try:
            self._repo.save_version(version)
            record_product_audit_entry(
                self._conn, action="CUTTING_VERSION_UPDATED", entity_id=version.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"scheme_id": scheme.id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("update cutting version failed op=%s",
                             command.operation_id)
            raise
        return CuttingResult(True, scheme.id, version.id, "CUTTING_VERSION_UPDATED")


class SubmitCuttingVersionUseCase(_BaseCuttingUseCase):
    name = "SubmitCuttingVersionUseCase"

    def execute(self, command: CuttingVersionTransitionCommand) -> CuttingResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return CuttingResult(False, None, None, "La versión no existe")
        try:
            version.submit()
        except ProductsDomainError as exc:
            return CuttingResult(False, version.cutting_scheme_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_CUTTING_SCHEME_CREATED,
                             command, "CUTTING_VERSION_SUBMITTED")


class ApproveCuttingVersionUseCase(_BaseCuttingUseCase):
    name = "ApproveCuttingVersionUseCase"

    def execute(self, command: CuttingVersionTransitionCommand) -> CuttingResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return CuttingResult(False, None, None, "La versión no existe")
        # NOTA (§39): a diferencia de Recipe/YieldProfileVersion, CuttingSchemeVersion
        # no registra `created_by` — no hay identidad de creador que segregar contra
        # el aprobador todavía. Ver docs/refactor memory products_enterprise_transformation.
        try:
            version.approve(approved_by_user_id=command.user_id or "",
                            reason=command.reason)
        except ProductsDomainError as exc:
            return CuttingResult(False, version.cutting_scheme_id, version.id, str(exc))
        return self._persist(version, ProductEvents.PRODUCT_CUTTING_SCHEME_CREATED,
                             command, "CUTTING_VERSION_APPROVED")


class ActivateCuttingVersionUseCase(_BaseCuttingUseCase):
    name = "ActivateCuttingVersionUseCase"

    def execute(self, command: CuttingVersionTransitionCommand) -> CuttingResult:
        command.validate()
        self._require(command.user_id)
        version = self._repo.get_version(command.version_id)
        if version is None:
            return CuttingResult(False, None, None, "La versión no existe")
        current = self._repo.active_version_for_scheme(version.cutting_scheme_id)
        try:
            version.activate()
            if current is not None and current.id != version.id:
                current.supersede()
        except ProductsDomainError as exc:
            return CuttingResult(False, version.cutting_scheme_id, version.id, str(exc))
        try:
            if current is not None and current.id != version.id:
                self._repo.save_version(current)
            self._repo.save_version(version)
            _emit(self._conn, ProductEvents.PRODUCT_CUTTING_SCHEME_ACTIVATED, command,
                  entity_id=version.id,
                  extra={"scheme_id": version.cutting_scheme_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("activate cutting version failed op=%s",
                             command.operation_id)
            raise
        return CuttingResult(True, version.cutting_scheme_id, version.id,
                             "CUTTING_VERSION_ACTIVATED")


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
