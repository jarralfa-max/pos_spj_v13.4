"""INV-27 repoint step 2 — strangler read adapter (canonical + legacy fallback)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.services.inventory.canonical_stock_read_adapter import (
    CanonicalStockReadAdapter,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed(conn, product, branch, qty):
    line = InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                        to_location_id=branch)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id=branch, warehouse_id=branch,
        source_module="procurement", source_document_type="GR",
        source_document_id=f"{product}{branch}", operation_id=f"{product}{branch}",
        created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


class TestAdapter:
    def test_flag_off_returns_legacy_even_if_canonical_present(self, conn):
        # Reads follow writes: flag OFF → legacy owns the truth, canonical is a
        # (possibly stale) snapshot, so the adapter serves legacy.
        _seed(conn, "p1", "b1", "10")
        adapter = CanonicalStockReadAdapter(
            lambda: conn, legacy_available=lambda p, b: 8.0, env={})
        assert adapter.available("p1", "b1") == Decimal("8.0")

    def test_flag_off_no_fallback_uses_canonical_best_effort(self, conn):
        _seed(conn, "p1", "b1", "10")
        adapter = CanonicalStockReadAdapter(lambda: conn, env={})  # no legacy
        assert adapter.available("p1", "b1") == Decimal("10")

    def test_cutover_on_is_authoritative_no_fallback(self, conn):
        _seed(conn, "p1", "b1", "10")
        adapter = CanonicalStockReadAdapter(
            lambda: conn, legacy_available=lambda p, b: 999,
            env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert adapter.available("p1", "b1") == Decimal("10")   # canonical, not legacy
        assert adapter.available("pX", "b1") == Decimal("0")    # missing → canonical 0

    def test_total_across_branches_when_no_branch(self, conn):
        _seed(conn, "p1", "b1", "10")
        _seed(conn, "p1", "b2", "4")
        adapter = CanonicalStockReadAdapter(
            lambda: conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert adapter.available("p1") == Decimal("14")

    def test_available_float_shim(self, conn):
        _seed(conn, "p1", "b1", "10")
        adapter = CanonicalStockReadAdapter(
            lambda: conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert adapter.available_float("p1", "b1") == 10.0

    def test_reserved_reduces_available(self, conn):
        _seed(conn, "p1", "b1", "10")
        conn.execute("UPDATE inventory_balances SET reserved_quantity='3'"
                     " WHERE product_id='p1' AND inventory_status='AVAILABLE'")
        conn.commit()
        adapter = CanonicalStockReadAdapter(
            lambda: conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert adapter.available("p1", "b1") == Decimal("7")


class _FakeReservations:
    def stock_disponible(self, pid):
        return 42.0


class TestAvailabilityServiceRepoint:
    """The legacy sell-availability reader now delegates to the canonical adapter
    (with the legacy reservation read as fallback) — backward-compatible."""

    def test_default_is_pure_legacy(self):
        from core.services.inventory_availability_service import (
            InventoryAvailabilityService,
        )
        svc = InventoryAvailabilityService(_FakeReservations())
        assert svc.disponible_para_venta(1) == 42.0
        assert svc.disponible_por_producto([1, 2]) == {1: 42.0, 2: 42.0}

    def test_flag_off_stays_legacy_flag_on_uses_canonical(self, conn):
        from core.services.inventory_availability_service import (
            InventoryAvailabilityService,
        )
        _seed(conn, "7", "b1", "9")
        # flag OFF → legacy owns writes, so the reader stays on legacy (42)
        off = InventoryAvailabilityService(
            _FakeReservations(), connection_provider=lambda: conn, env={})
        assert off.disponible_para_venta(7) == 42.0
        # flag ON → canonical is authoritative (product 7 = 9; missing = 0)
        on = InventoryAvailabilityService(
            _FakeReservations(), connection_provider=lambda: conn,
            env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert on.disponible_para_venta(7) == 9.0
        assert on.disponible_para_venta(99) == 0.0


class TestStockReservationRepoint:
    def _legacy(self, conn):
        conn.execute("CREATE TABLE IF NOT EXISTS stock_reservas (id TEXT, estado TEXT,"
                     " branch_id TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS stock_reserva_detalles (id TEXT,"
                     " reserva_id TEXT, producto_id TEXT, cantidad REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS inventory_stock (product_id TEXT,"
                     " branch_id TEXT, quantity REAL, unit TEXT)")
        conn.execute("INSERT INTO inventory_stock VALUES ('7','b1',50.0,'u')")
        conn.commit()

    def test_flag_off_uses_legacy_stock(self, conn):
        from core.services.stock_reservation_service import StockReservationService
        self._legacy(conn)
        _seed(conn, "7", "b1", "9")
        svc = StockReservationService(conn, "b1", env={})
        assert svc.stock_disponible("7") == 50.0  # legacy inventory_stock

    def test_flag_on_uses_canonical(self, conn):
        from core.services.stock_reservation_service import StockReservationService
        self._legacy(conn)
        _seed(conn, "7", "b1", "9")
        svc = StockReservationService(conn, "b1", env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        assert svc.stock_disponible("7") == 9.0  # canonical projection
