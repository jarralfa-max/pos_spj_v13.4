"""Use cases del catálogo externo (PROD-15) — buscar, hacer match, revisar,
aprobar/rechazar e importar registros externos.

`ExternalCatalogRepository` (fuentes/registros/lotes + lookups de matching),
`ExternalProductCatalogGateway`/`ProviderRegistry`, `ProductMatchingService` y
`external_data_acceptance_policy.ensure_importable` existían completos —
dominio, infraestructura HTTP (Open Food Facts) y persistencia — pero CERO
casos de uso reales los orquestaban (confirmado por grep): ningún flujo
buscar → match → revisar → aprobar → importar existía en la aplicación.

**Segregación (§39) — gap conocido, no fabricado**: `ExternalProductRecord`
no tiene campo `created_by`/`staged_by` (a diferencia de `RecipeVersion`, que
sí lo tiene) — no hay identidad de "quien buscó" contra la cual segregar
"quien aprueba" todavía. `ProductPermissions.EXTERNAL_APPROVE` está mapeado a
`EXTERNAL_IMPORT` en `SEGREGATED_APPROVALS`, pero sin esa identidad la
segregación real no puede aplicarse aquí — mismo tipo de hueco documentado
para `CuttingSchemeVersion`/`BundleVersion` en PROD-3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_external_catalog_commands import (
    ApproveExternalRecordCommand,
    ImportExternalRecordCommand,
    RejectExternalRecordCommand,
    SearchExternalCatalogCommand,
)
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.policies.external_data_acceptance_policy import (
    ensure_importable,
)
from backend.domain.products.services.product_matching_service import (
    ProductMatchingService,
)
from backend.infrastructure.db.repositories.products.external_catalog_repository import (
    ExternalCatalogRepository,
)
from backend.infrastructure.product_catalogs.external_product_catalog_gateway import (
    ExternalProductCatalogGateway,
)

logger = logging.getLogger("spj.products.external_catalog_use_cases")


@dataclass(frozen=True)
class ExternalCatalogResult:
    success: bool
    entity_id: str | None
    message: str
    record_ids: tuple[str, ...] = ()


class _Base:
    def __init__(self, connection, registry,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ExternalCatalogRepository(connection)
        self._registry = registry
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class SearchExternalCatalogUseCase(_Base):
    """Busca en la fuente externa, intenta match automático (barcode → nombre) y
    deja cada resultado en staging (PENDING_REVIEW o MATCHED)."""
    name = "SearchExternalCatalogUseCase"

    def execute(self, command: SearchExternalCatalogCommand) -> ExternalCatalogResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EXTERNAL_SEARCH)
        source = self._repo.get_source(command.source_id)
        if source is None:
            return ExternalCatalogResult(False, None, "La fuente externa no existe")
        gateway = ExternalProductCatalogGateway(self._registry)
        matcher = ProductMatchingService()
        try:
            records = gateway.search(source, command.query)
        except ProductsDomainError as exc:
            return ExternalCatalogResult(False, None, str(exc))
        record_ids = []
        try:
            for record in records:
                matched = matcher.match(
                    record, by_barcode=self._repo.barcode_lookup(),
                    by_normalized_name=self._repo.name_lookup())
                if matched:
                    record.mark_matched(matched)
                self._repo.save_record(record)
                record_ids.append(record.id)
            record_product_audit_entry(
                self._conn, action="EXTERNAL_CATALOG_SEARCHED",
                entity_id=command.source_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"query": command.query, "results": len(records)})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("search external catalog failed op=%s",
                             command.operation_id)
            raise
        return ExternalCatalogResult(
            True, command.source_id, "EXTERNAL_CATALOG_SEARCHED",
            record_ids=tuple(record_ids))


class ApproveExternalRecordUseCase(_Base):
    name = "ApproveExternalRecordUseCase"

    def execute(self, command: ApproveExternalRecordCommand) -> ExternalCatalogResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EXTERNAL_APPROVE)
        record = self._repo.get_record(command.record_id)
        if record is None:
            return ExternalCatalogResult(False, None, "El registro externo no existe")
        try:
            record.approve()
        except ProductsDomainError as exc:
            return ExternalCatalogResult(False, None, str(exc))
        try:
            self._repo.save_record(record)
            record_product_audit_entry(
                self._conn, action="EXTERNAL_PRODUCT_IMPORT_APPROVED",
                entity_id=record.id, user_id=command.user_id,
                operation_id=command.operation_id)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("approve external record failed op=%s",
                             command.operation_id)
            raise
        return ExternalCatalogResult(True, record.id, "EXTERNAL_PRODUCT_IMPORT_APPROVED")


class RejectExternalRecordUseCase(_Base):
    name = "RejectExternalRecordUseCase"

    def execute(self, command: RejectExternalRecordCommand) -> ExternalCatalogResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EXTERNAL_REVIEW)
        record = self._repo.get_record(command.record_id)
        if record is None:
            return ExternalCatalogResult(False, None, "El registro externo no existe")
        record.reject()
        try:
            self._repo.save_record(record)
            record_product_audit_entry(
                self._conn, action="EXTERNAL_RECORD_REJECTED", entity_id=record.id,
                user_id=command.user_id, operation_id=command.operation_id)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("reject external record failed op=%s",
                             command.operation_id)
            raise
        return ExternalCatalogResult(True, record.id, "EXTERNAL_RECORD_REJECTED")


class ImportExternalRecordUseCase(_Base):
    """Importa un registro ya revisado (§15: nunca sin revisión). Un registro
    MATCHED sólo se cierra (ya está vinculado a un producto existente); uno
    APPROVED sin match crea un producto nuevo — el catálogo externo no conoce
    la clasificación interna, por eso el command trae tipo/unidad/categoría."""
    name = "ImportExternalRecordUseCase"

    def __init__(self, connection, registry,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        super().__init__(connection, registry, authorization)
        self._create_product = CreateProductMasterUseCase(connection, self._auth)

    def execute(self, command: ImportExternalRecordCommand) -> ExternalCatalogResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.IMPORT_EXECUTE)
        record = self._repo.get_record(command.record_id)
        if record is None:
            return ExternalCatalogResult(False, None, "El registro externo no existe")
        try:
            ensure_importable(record)
        except ProductsDomainError as exc:
            return ExternalCatalogResult(False, None, str(exc))
        product_id = record.matched_product_id
        if product_id is None:
            if not command.base_unit_id:
                return ExternalCatalogResult(
                    False, None, "base_unit_id es requerido para crear un producto nuevo")
            created = self._create_product.execute(CreateProductMasterCommand(
                operation_id=command.operation_id, code="", auto_generate_code=True,
                name=record.name, product_type=command.product_type,
                base_unit_id=command.base_unit_id, category_id=command.category_id,
                user_id=command.user_id))
            if not created.success:
                return ExternalCatalogResult(False, None, created.message)
            product_id = created.product_id
        try:
            record.mark_imported()
        except ProductsDomainError as exc:
            return ExternalCatalogResult(False, None, str(exc))
        try:
            self._repo.save_record(record)
            record_product_audit_entry(
                self._conn, action="EXTERNAL_RECORD_IMPORTED", entity_id=record.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"product_id": product_id})
            _emit(self._conn, ProductEvents.EXTERNAL_PRODUCT_IMPORT_APPROVED, command,
                 record.id, {"product_id": product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("import external record failed op=%s",
                             command.operation_id)
            raise
        return ExternalCatalogResult(True, product_id, "EXTERNAL_RECORD_IMPORTED")


def _emit(conn, event_name: str, command, entity_id: str, extra: dict) -> None:
    import json
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
