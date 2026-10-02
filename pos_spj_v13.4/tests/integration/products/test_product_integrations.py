"""PROD-17 — integraciones por product_id: Inventory/Purchasing/POS/Quality + calidad."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import (
    ProductsAuthorizationPolicy,
)
from backend.application.products.event_handlers.quality_status_handler import (
    QualityStatusHandler,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.integration_query_services import (
    InventoryProductConfigQueryService,
    PosCatalogQueryService,
    PurchaseProductConfigQueryService,
    QualityProductConfigQueryService,
)
from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


def _add_product(c, pid, ptype="RESALE_PRODUCT", status="ACTIVE", **flags):
    cols = dict(sellable=0, purchasable=0, inventory_managed=0, internal_only=0,
                lot_controlled=0, serial_controlled=0, expiration_controlled=0,
                catch_weight_enabled=0, quality_controlled=0, traceability_required=0,
                species_id=None, tax_profile_id=None)
    cols.update(flags)
    c.execute(
        """INSERT INTO products (id,code,name,name_normalized,product_type,
           lifecycle_status,base_unit_id,species_id,tax_profile_id,sellable,purchasable,
           inventory_managed,internal_only,lot_controlled,serial_controlled,
           expiration_controlled,catch_weight_enabled,quality_controlled,traceability_required)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, pid.upper(), pid, pid, ptype, status, "kg", cols["species_id"],
         cols["tax_profile_id"], cols["sellable"], cols["purchasable"],
         cols["inventory_managed"], cols["internal_only"], cols["lot_controlled"],
         cols["serial_controlled"], cols["expiration_controlled"],
         cols["catch_weight_enabled"], cols["quality_controlled"],
         cols["traceability_required"]))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


# ── Inventory config (§30) ───────────────────────────────────────────────────
class TestInventoryConfig:
    def test_flags_exposed(self, conn):
        _add_product(conn, "p1", inventory_managed=1, lot_controlled=1,
                     expiration_controlled=1, traceability_required=1)
        dto = InventoryProductConfigQueryService(conn).get("p1")
        assert dto.inventory_managed and dto.lot_controlled and dto.traceability_required
        assert dto.base_unit_id == "kg"

    def test_no_balance_fields(self, conn):
        _add_product(conn, "p1")
        dto = InventoryProductConfigQueryService(conn).get("p1")
        for forbidden in ("balance", "on_hand", "existencia", "stock", "quantity"):
            assert not hasattr(dto, forbidden)


# ── Purchasing config (§31) ──────────────────────────────────────────────────
class TestPurchaseConfig:
    def test_purchase_config_with_supplier_codes(self, conn):
        _add_product(conn, "p1", ptype="PRIMARY_CUT", purchasable=1, species_id="bov",
                     catch_weight_enabled=1)
        conn.execute("INSERT INTO product_alternate_codes (id,product_id,code,code_type,"
                     "active) VALUES ('a1','p1','SUP-9','SUPPLIER_CODE',1)")
        ProfileRepository(conn).save_logistics(
            ProductLogisticsProfile(product_id="p1", frozen=True))
        dto = PurchaseProductConfigQueryService(conn).get("p1")
        assert dto.purchasable and dto.is_meat and dto.requires_cold_chain
        assert dto.supplier_codes == ("SUP-9",)

    def test_no_price_field(self, conn):
        _add_product(conn, "p1", purchasable=1)
        dto = PurchaseProductConfigQueryService(conn).get("p1")
        for forbidden in ("price", "precio", "cost", "unit_price"):
            assert not hasattr(dto, forbidden)


# ── Unidades de compra (FASE 3 Compras, 2026-09-25) ───────────────────────────
def _units(c):
    for uid, code, name, dim in (("u-kg", "KG", "Kilogramo", "WEIGHT"),
                                 ("u-g", "G", "Gramo", "WEIGHT"),
                                 ("u-caja", "CAJA", "Caja", "PACKAGE"),
                                 ("u-pza", "PZA", "Pieza", "COUNT")):
        c.execute("INSERT OR IGNORE INTO units_of_measure (id, code, name, dimension)"
                  " VALUES (?,?,?,?)", (uid, code, name, dim))


def _conversion(c, cid, frm, to, factor, product_id="p1", active=1, effective_to=None):
    c.execute("INSERT INTO product_unit_conversions (id, product_id, from_unit_id, to_unit_id,"
              " factor, rounding_scale, active, effective_to) VALUES (?,?,?,?,?,6,?,?)",
              (cid, product_id, frm, to, factor, active, effective_to))


class TestPurchaseUnits:
    """Compras NO define unidades: las lee de aquí. La base va primero con factor
    1; cada presentación del producto se expresa en unidades base."""

    def test_base_unit_only_when_nothing_configured(self, conn):
        _units(conn)
        _add_product(conn, "p1", purchasable=1)
        conn.execute("UPDATE products SET base_unit_id='u-kg'")
        dto = PurchaseProductConfigQueryService(conn).get("p1")
        assert (dto.base_unit_code, dto.base_unit_name, dto.base_unit_dimension) == (
            "KG", "Kilogramo", "WEIGHT")
        assert [(u.code, u.factor_to_base, u.is_base) for u in dto.purchase_units] == [
            ("KG", "1", True)]

    def test_presentations_expressed_in_base_units(self, conn):
        _units(conn)
        _add_product(conn, "p1", purchasable=1)
        conn.execute("UPDATE products SET base_unit_id='u-kg'")
        _conversion(conn, "c1", "u-caja", "u-kg", "20")          # 1 caja = 20 kg
        _conversion(conn, "c2", "u-kg", "u-g", "1000")           # inversa: 1 g = 0.001 kg
        _conversion(conn, "c3", "u-pza", "u-kg", "2", active=0)  # inactiva: no se ofrece
        _conversion(conn, "c4", "u-pza", "u-kg", "3", effective_to="2000-01-01")  # vencida
        _conversion(conn, "c5", "u-caja", "u-kg", "25", product_id="otro")  # de otro producto
        units = {u.code: u for u in PurchaseProductConfigQueryService(conn).get("p1").purchase_units}
        assert set(units) == {"KG", "CAJA", "G"}
        assert units["CAJA"].factor_to_base == "20" and units["CAJA"].product_specific
        assert units["G"].factor_to_base == "0.001"

    def test_product_specific_conversion_wins_over_global(self, conn):
        _units(conn)
        _add_product(conn, "p1", purchasable=1)
        conn.execute("UPDATE products SET base_unit_id='u-kg'")
        _conversion(conn, "g1", "u-caja", "u-kg", "10", product_id=None)
        _conversion(conn, "c1", "u-caja", "u-kg", "18")
        units = {u.code: u for u in PurchaseProductConfigQueryService(conn).get("p1").purchase_units}
        assert units["CAJA"].factor_to_base == "18"

    def test_price_basis_only_for_enabled_catch_weight(self, conn):
        _units(conn)
        _add_product(conn, "p1", purchasable=1, catch_weight_enabled=1)
        conn.execute("INSERT INTO product_catch_weight_config (product_id, enabled,"
                     " nominal_unit_id, weight_unit_id, price_basis, tolerance_pct)"
                     " VALUES ('p1', 1, 'u-pza', 'u-kg', 'PER_KILOGRAM', '0')")
        assert PurchaseProductConfigQueryService(conn).get("p1").price_basis == "PER_KILOGRAM"

    def test_tolerates_reduced_schema_and_plain_tuples(self):
        """Hay tablas `products` hechas a mano por todo el repo y conexiones sin
        `sqlite3.Row`: el contrato degrada, no revienta."""
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE products (id TEXT, code TEXT, name TEXT, base_unit_id TEXT)")
        c.execute("INSERT INTO products VALUES ('p1', 'P1', 'Pollo', 'PZA')")
        dto = PurchaseProductConfigQueryService(c).get("p1")
        assert dto.base_unit_code == "PZA" and dto.purchasable
        assert [u.code for u in dto.purchase_units] == ["PZA"]


# ── POS (§33) ────────────────────────────────────────────────────────────────
class TestPosCatalog:
    def test_active_sellable_offered(self, conn):
        _add_product(conn, "p1", sellable=1)
        conn.execute("INSERT INTO branch_product (id,product_id,branch_id,enabled) "
                     "VALUES ('bp1','p1','b1',1)")
        conn.execute("INSERT INTO product_barcodes (id,product_id,barcode_value,"
                     "barcode_type,is_primary,active) VALUES ('bc1','p1','SKU1','INTERNAL_SKU',1,1)")
        svc = PosCatalogQueryService(conn)
        dto = svc.get("p1")
        assert dto.sellable_now and dto.primary_barcode == "SKU1"
        assert svc.is_offered_at_branch("p1", "b1")
        assert not svc.is_offered_at_branch("p1", "b2")

    def test_internal_not_sellable(self, conn):
        _add_product(conn, "wip", ptype="SEMI_FINISHED_GOOD", sellable=0, internal_only=1)
        assert not PosCatalogQueryService(conn).get("wip").sellable_now

    def test_draft_not_sellable(self, conn):
        _add_product(conn, "p1", status="DRAFT", sellable=1)
        assert not PosCatalogQueryService(conn).get("p1").sellable_now

    def test_no_price_field(self, conn):
        _add_product(conn, "p1", sellable=1)
        dto = PosCatalogQueryService(conn).get("p1")
        for forbidden in ("price", "precio", "unit_price"):
            assert not hasattr(dto, forbidden)


# ── Quality config (§34) ─────────────────────────────────────────────────────
class TestQualityConfig:
    def test_quality_requirements(self, conn):
        _add_product(conn, "p1", ptype="PRIMARY_CUT", quality_controlled=1, species_id="bov")
        ProfileRepository(conn).save_quality(
            ProductQualityProfile(product_id="p1", inspection_required=True,
                                  quarantine_required=True))
        dto = QualityProductConfigQueryService(conn).get("p1")
        assert dto.inspection_required and dto.quarantine_required


# ── Quality → commercial state handler (§34) ─────────────────────────────────
class TestQualityStatusHandler:
    def _authz(self, granted):
        class _C:
            def has_permission(self, u, p): return p in granted
        return ProductsAuthorizationPolicy(_C())

    def test_block_moves_active_to_blocked(self, conn):
        _add_product(conn, "p1", sellable=1)
        h = QualityStatusHandler(conn, authorization=self._authz({ProductPermissions.BLOCK}))
        assert h.handle(ProductEvents.PRODUCT_QUALITY_BLOCKED,
                        {"event_id": "e1", "product_id": "p1", "user_id": "q1"})
        assert conn.execute("SELECT lifecycle_status FROM products WHERE id='p1'"
                            ).fetchone()[0] == "BLOCKED"
        audit = conn.execute("SELECT COUNT(*) FROM product_audit_log "
                             "WHERE entity_id='p1'").fetchone()[0]
        assert audit == 1

    def test_release_moves_blocked_to_active(self, conn):
        _add_product(conn, "p1", status="BLOCKED", sellable=1)
        h = QualityStatusHandler(conn, authorization=self._authz({ProductPermissions.ACTIVATE}))
        assert h.handle(ProductEvents.PRODUCT_QUALITY_RELEASED,
                        {"event_id": "e2", "product_id": "p1", "user_id": "q1"})
        assert conn.execute("SELECT lifecycle_status FROM products WHERE id='p1'"
                            ).fetchone()[0] == "ACTIVE"

    def test_idempotent_by_event_id(self, conn):
        _add_product(conn, "p1", sellable=1)
        h = QualityStatusHandler(conn, authorization=self._authz({ProductPermissions.BLOCK}))
        h.handle(ProductEvents.PRODUCT_QUALITY_BLOCKED, {"event_id": "e1", "product_id": "p1"})
        assert not h.handle(ProductEvents.PRODUCT_QUALITY_BLOCKED,
                            {"event_id": "e1", "product_id": "p1"})

    def test_block_requires_permission(self, conn):
        _add_product(conn, "p1", sellable=1)
        h = QualityStatusHandler(conn, authorization=self._authz(set()))
        with pytest.raises(ProductPermissionDeniedError):
            h.handle(ProductEvents.PRODUCT_QUALITY_BLOCKED,
                     {"event_id": "e1", "product_id": "p1", "user_id": "q1"})

    def test_no_stock_touch(self, conn):
        # el handler nunca escribe tablas de inventario (no existen aquí);
        # sólo cambia lifecycle_status y audita.
        _add_product(conn, "p1", sellable=1, inventory_managed=1)
        h = QualityStatusHandler(conn, authorization=self._authz({ProductPermissions.BLOCK}))
        h.handle(ProductEvents.PRODUCT_QUALITY_BLOCKED, {"event_id": "e1", "product_id": "p1"})
        # sin errores por tablas de balance ausentes → prueba implícita
        assert True
