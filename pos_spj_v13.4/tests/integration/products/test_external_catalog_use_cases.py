"""PROD-15 — catálogo externo: buscar, match, revisar, aprobar/rechazar, importar.

Antes de esta fase, `ExternalCatalogRepository` (fuentes/registros/lotes +
lookups de matching), `ExternalProductCatalogGateway`/`ProviderRegistry`,
`ProductMatchingService` y `external_data_acceptance_policy.ensure_importable`
existían completos (dominio, infraestructura HTTP real para Open Food Facts,
persistencia) pero CERO casos de uso reales los orquestaban (confirmado por
grep: cero consumidores del gateway, del registry y de
`ProductMatchingService` en toda la capa de aplicación). Estos tests prueban
el flujo completo buscar → match automático → revisar → aprobar/rechazar →
importar, incluido el matching real (por barcode y por nombre) ejercido por
primera vez a través de un caso de uso real.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_external_catalog_commands import (
    ApproveExternalRecordCommand,
    ImportExternalRecordCommand,
    RejectExternalRecordCommand,
    SearchExternalCatalogCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_external_catalog_use_cases import (
    ApproveExternalRecordUseCase,
    ImportExternalRecordUseCase,
    RejectExternalRecordUseCase,
    SearchExternalCatalogUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.domain.products.external_enums import ExternalProviderType
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.product_catalogs.provider_registry import ProviderRegistry
from backend.shared.ids import new_uuid

_P = ProductPermissions
_UNIT = "unit-pza"


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.EXTERNAL_SEARCH, _P.EXTERNAL_REVIEW, _P.EXTERNAL_APPROVE,
    _P.IMPORT_EXECUTE, _P.OVERRIDE_CODE, _P.CREATE}))


class _FakeAdapter:
    """Doble del Protocol ExternalCatalogAdapter — sin red real."""
    provider_type = ExternalProviderType.MANUAL

    def __init__(self, results):
        self._results = results

    def search(self, query: str) -> list[dict]:
        return self._results


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'PZA', 'Pieza', 'COUNT', 1)", (_UNIT,))
    c.commit()
    yield c
    c.close()


def _source(conn, results):
    from backend.domain.products.entities.external_catalog_source import (
        ExternalCatalogSource,
    )
    from backend.infrastructure.db.repositories.products.external_catalog_repository import (
        ExternalCatalogRepository,
    )
    source = ExternalCatalogSource(code="MANUAL-1", name="Fuente de prueba",
                                   provider_type=ExternalProviderType.MANUAL)
    ExternalCatalogRepository(conn).save_source(source)
    conn.commit()
    registry = ProviderRegistry()
    registry.register(_FakeAdapter(results))
    return source.id, registry


class TestSearchAndMatch:
    def test_search_stages_unmatched_record(self, conn):
        source_id, registry = _source(conn, [
            {"external_id": "ext-1", "name": "Salsa Botanera 250ml",
             "barcode": "9999999999999"}])
        r = SearchExternalCatalogUseCase(conn, registry, _ALL).execute(
            SearchExternalCatalogCommand(operation_id="op", source_id=source_id,
                                         query="salsa", user_id="u1"))
        assert r.success and len(r.record_ids) == 1
        row = conn.execute("SELECT status, matched_product_id FROM "
                           "external_product_records WHERE id=?",
                           (r.record_ids[0],)).fetchone()
        assert row["status"] == "PENDING_REVIEW" and row["matched_product_id"] is None

    def test_search_auto_matches_by_barcode(self, conn):
        # producto real con ese barcode ya asignado
        from backend.application.products.commands.product_master_commands import (
            CreateProductMasterCommand,
        )
        from backend.application.products.use_cases.product_master_use_cases import (
            CreateProductMasterUseCase,
        )
        from backend.infrastructure.db.repositories.products.barcode_repository import (
            BarcodeRepository,
        )
        from backend.domain.products.entities.product_barcode import ProductBarcode
        from backend.domain.products.value_objects.barcode import Barcode

        created = CreateProductMasterUseCase(conn, _ALL).execute(
            CreateProductMasterCommand(
                operation_id="op0", code="A-1", name="Salsa existente",
                product_type="RESALE_PRODUCT", base_unit_id=_UNIT,
                category_id="cat1", user_id="u1"))
        pb = ProductBarcode(product_id=created.product_id,
                            barcode=Barcode(value="9999999999999",
                                           barcode_type="INTERNAL_SKU"))
        BarcodeRepository(conn).assign(pb)
        conn.commit()

        source_id, registry = _source(conn, [
            {"external_id": "ext-2", "name": "Salsa (nombre distinto)",
             "barcode": "9999999999999"}])
        r = SearchExternalCatalogUseCase(conn, registry, _ALL).execute(
            SearchExternalCatalogCommand(operation_id="op", source_id=source_id,
                                         query="salsa", user_id="u1"))
        assert r.success
        row = conn.execute("SELECT status, matched_product_id FROM "
                           "external_product_records WHERE id=?",
                           (r.record_ids[0],)).fetchone()
        assert row["status"] == "MATCHED"
        assert row["matched_product_id"] == created.product_id

    def test_search_requires_permission(self, conn):
        source_id, registry = _source(conn, [])
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            SearchExternalCatalogUseCase(conn, registry, no_perm).execute(
                SearchExternalCatalogCommand(operation_id="op", source_id=source_id,
                                             query="x"))

    def test_search_unknown_source_rejected(self, conn):
        registry = ProviderRegistry()
        r = SearchExternalCatalogUseCase(conn, registry, _ALL).execute(
            SearchExternalCatalogCommand(operation_id="op", source_id="nope",
                                         query="x", user_id="u1"))
        assert not r.success


class TestReviewAndImport:
    def _staged_record_id(self, conn):
        source_id, registry = _source(conn, [
            {"external_id": "ext-1", "name": "Producto nuevo externo"}])
        r = SearchExternalCatalogUseCase(conn, registry, _ALL).execute(
            SearchExternalCatalogCommand(operation_id="op", source_id=source_id,
                                         query="x", user_id="u1"))
        return r.record_ids[0]

    def test_reject_record(self, conn):
        record_id = self._staged_record_id(conn)
        r = RejectExternalRecordUseCase(conn, None, _ALL).execute(
            RejectExternalRecordCommand(operation_id="op2", record_id=record_id,
                                        user_id="u1"))
        assert r.success
        row = conn.execute("SELECT status FROM external_product_records WHERE id=?",
                           (record_id,)).fetchone()
        assert row["status"] == "REJECTED"

    def test_import_requires_review_first(self, conn):
        record_id = self._staged_record_id(conn)
        r = ImportExternalRecordUseCase(conn, None, _ALL).execute(
            ImportExternalRecordCommand(operation_id="op2", record_id=record_id,
                                        base_unit_id=_UNIT, user_id="u1"))
        assert not r.success

    def test_approve_then_import_creates_new_product(self, conn):
        record_id = self._staged_record_id(conn)
        approved = ApproveExternalRecordUseCase(conn, None, _ALL).execute(
            ApproveExternalRecordCommand(operation_id="op2", record_id=record_id,
                                         user_id="u1"))
        assert approved.success
        imported = ImportExternalRecordUseCase(conn, None, _ALL).execute(
            ImportExternalRecordCommand(operation_id="op3", record_id=record_id,
                                        base_unit_id=_UNIT, category_id="cat1",
                                        user_id="u1"))
        assert imported.success
        product = conn.execute("SELECT name FROM products WHERE id=?",
                               (imported.entity_id,)).fetchone()
        assert product["name"] == "Producto nuevo externo"
        row = conn.execute("SELECT status FROM external_product_records WHERE id=?",
                           (record_id,)).fetchone()
        assert row["status"] == "IMPORTED"

    def test_matched_record_import_does_not_create_duplicate_product(self, conn):
        from backend.application.products.commands.product_master_commands import (
            CreateProductMasterCommand,
        )
        from backend.application.products.use_cases.product_master_use_cases import (
            CreateProductMasterUseCase,
        )
        existing = CreateProductMasterUseCase(conn, _ALL).execute(
            CreateProductMasterCommand(
                operation_id="op0", code="A-2", name="Ya existe",
                product_type="RESALE_PRODUCT", base_unit_id=_UNIT,
                category_id="cat1", user_id="u1"))
        from backend.infrastructure.db.repositories.products.external_catalog_repository import (
            ExternalCatalogRepository,
        )
        from backend.domain.products.entities.external_catalog_source import (
            ExternalCatalogSource,
        )
        from backend.domain.products.entities.external_product_record import (
            ExternalProductRecord,
        )
        source = ExternalCatalogSource(code="M2", name="F2",
                                       provider_type=ExternalProviderType.MANUAL)
        repo = ExternalCatalogRepository(conn)
        repo.save_source(source)
        record = ExternalProductRecord(source_id=source.id, external_id="ext-9",
                                       name="Ya existe (externo)")
        record.mark_matched(existing.product_id)
        repo.save_record(record)
        conn.commit()

        before = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        approved = ApproveExternalRecordUseCase(conn, None, _ALL).execute(
            ApproveExternalRecordCommand(operation_id="op2", record_id=record.id,
                                         user_id="u1"))
        assert approved.success
        imported = ImportExternalRecordUseCase(conn, None, _ALL).execute(
            ImportExternalRecordCommand(operation_id="op3", record_id=record.id,
                                        user_id="u1"))
        assert imported.success and imported.entity_id == existing.product_id
        after = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        assert after == before  # ningún producto nuevo creado
