"""SALES-9/POS-9 — inventory reservation: Reserve, Confirm, Release, Expire.

Builds `stock_reservas`/`stock_reserva_detalles`/`inventory_stock` by hand
(the exact DDL from migrations/m000_base_schema.py's `_create_ventas` block,
not a full migration run) alongside the real `create_sales_schema` — same
"hand-roll only what's queried" style as
tests/test_ventas_customer_dialog_regression.py, chosen over a full
199-migration bootstrap for speed.

This suite is also the regression test for two real, previously-undiscovered
bugs found and fixed in this phase, in
`core/services/stock_reservation_service.py::StockReservationService.reservar`:
(1) `int(item["id"])` on the payload — incompatible with UUIDv7 product ids;
(2) `stock_reservas.id`/`stock_reserva_detalles.id` (both `TEXT NOT NULL
PRIMARY KEY`, no DEFAULT) were never included in their own INSERT statements
— `reservar()` unconditionally raised `NOT NULL constraint failed` against
the real schema, for ANY caller, not just UUIDv7 ones. See
docs/refactor/SALES-9_reservas_inventario.md for the full story (confirmed
by executing the method directly, not just reading it).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.result import SaleResult
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.inventory_use_cases import (
    ConfirmInventoryReservationUseCase,
    ExpireOrphanedInventoryReservationsUseCase,
    ReleaseInventoryReservationUseCase,
    ReserveInventoryForSaleUseCase,
)
from backend.application.sales.use_cases.lifecycle_use_cases import CancelSaleUseCase, SuspendSaleUseCase
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.domain.sales.exceptions import InventoryReservationFailedError
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_inventory_client import SalesInventoryClient
from backend.shared.ids import new_uuid


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    create_sales_schema(c)
    c.execute("""
        CREATE TABLE inventory_stock (
            branch_id TEXT, product_id TEXT, quantity REAL
        )
    """)
    c.execute("""
        CREATE TABLE stock_reservas (
            id           TEXT NOT NULL PRIMARY KEY,
            folio        TEXT UNIQUE,
            branch_id    TEXT NOT NULL,
            estado       TEXT NOT NULL DEFAULT 'activa',
            payload_json TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now')),
            expires_at   TEXT DEFAULT (datetime('now', '+30 minutes'))
        )
    """)
    c.execute("""
        CREATE TABLE stock_reserva_detalles (
            id          TEXT NOT NULL PRIMARY KEY,
            reserva_id  TEXT NOT NULL REFERENCES stock_reservas(id),
            producto_id TEXT NOT NULL,
            cantidad    REAL NOT NULL,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


def _seed_stock(conn, *, branch_id: str, product_id: str, quantity: float) -> None:
    conn.execute("INSERT INTO inventory_stock (branch_id, product_id, quantity) VALUES (?,?,?)",
                 (branch_id, product_id, quantity))
    conn.commit()


def _sale_with_line(conn, *, branch_id, product_id, quantity="2") -> str:
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal(quantity),
        unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
    return sale_id


class TestSalesInventoryClient:
    def test_reserve_for_sale_with_uuidv7_product_id(self, conn):
        """Regression for bug (1): a UUIDv7 product_id must not raise
        ValueError from an int() cast."""
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        sale = SaleRepository(conn).get(sale_id)

        client = SalesInventoryClient(conn, branch_id=branch_id)
        reservation_id = client.reserve_for_sale(sale)
        conn.commit()

        assert reservation_id
        row = conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                           (reservation_id,)).fetchone()
        assert row == ("activa",)

    def test_reserve_insufficient_stock_raises_domain_error(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=1.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id, quantity="5")
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        sale = SaleRepository(conn).get(sale_id)

        client = SalesInventoryClient(conn, branch_id=branch_id)
        with pytest.raises(InventoryReservationFailedError):
            client.reserve_for_sale(sale)

    def test_confirm_and_release(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        sale = SaleRepository(conn).get(sale_id)
        client = SalesInventoryClient(conn, branch_id=branch_id)
        reservation_id = client.reserve_for_sale(sale)
        conn.commit()

        client.confirm(reservation_id, sale_id=sale.id, folio=sale.id)
        conn.commit()
        assert conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                            (reservation_id,)).fetchone() == ("confirmada",)

    def test_release(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        sale = SaleRepository(conn).get(sale_id)
        client = SalesInventoryClient(conn, branch_id=branch_id)
        reservation_id = client.reserve_for_sale(sale)
        conn.commit()

        client.release(reservation_id, reason="cancelada")
        conn.commit()
        assert conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                            (reservation_id,)).fetchone() == ("cancelada",)

    def test_expire_orphaned_returns_count(self, conn):
        branch_id = new_uuid()
        client = SalesInventoryClient(conn, branch_id=branch_id)
        assert client.expire_orphaned() == 0


class TestReservationUseCases:
    def test_reserve_use_case_is_idempotent(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        cashier = new_uuid()

        first = ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert first.success
        first_reservation_id = first.data["reservation_id"]

        second = ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert second.success
        assert second.data["reservation_id"] == first_reservation_id

        count = conn.execute("SELECT COUNT(*) FROM stock_reservas").fetchone()[0]
        assert count == 1

    def test_reserve_use_case_insufficient_stock_fails_cleanly(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=1.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id, quantity="5")
        result = ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success

    def test_confirm_use_case(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        cashier = new_uuid()
        ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        result = ConfirmInventoryReservationUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success

    def test_confirm_use_case_without_reservation_is_a_noop_ok(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        result = ConfirmInventoryReservationUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success

    def test_release_use_case(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        cashier = new_uuid()
        reserve = ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        result = ReleaseInventoryReservationUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success
        assert result.data["sale"].id == sale_id

        row = conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                           (reserve.data["reservation_id"],)).fetchone()
        assert row == ("cancelada",)

    def test_expire_orphaned_use_case(self, conn):
        branch_id = new_uuid()
        count = ExpireOrphanedInventoryReservationsUseCase().execute(conn, branch_id=branch_id)
        assert count == 0


class TestSuspendReservesInventoryForReal:
    """§20: 'Al agregar productos: ReserveInventoryForSaleUseCase' — the real
    integration point in this codebase (mirroring legacy
    modulos/ventas.py::suspender_venta) is at SUSPEND time, not per-line."""

    def test_suspend_reserves_inventory(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        cashier = new_uuid()
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        cashier = SaleRepository(conn).get(sale_id).cashier_user_id

        result = SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)

        assert result.success
        assert result.data["sale"].status == "SUSPENDED"
        reservation_id = SaleRepository(conn).get(sale_id).inventory_reservation_id
        assert reservation_id is not None
        row = conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                           (reservation_id,)).fetchone()
        assert row == ("activa",)

    def test_suspend_fails_when_stock_insufficient_and_does_not_suspend(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=1.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id, quantity="5")
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        cashier = SaleRepository(conn).get(sale_id).cashier_user_id

        result = SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)

        assert not result.success
        # The sale must remain ACTIVE — suspend+reserve is all-or-nothing.
        reloaded = SaleRepository(conn).get(sale_id)
        assert reloaded.status.value == "ACTIVE"
        assert reloaded.inventory_reservation_id is None


class TestCancelReleasesInventoryForReal:
    def test_cancel_releases_the_reservation(self, conn):
        branch_id = new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10.0)
        sale_id = _sale_with_line(conn, branch_id=branch_id, product_id=product_id)
        from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
        cashier = SaleRepository(conn).get(sale_id).cashier_user_id

        SuspendSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            max_suspended_sales=5)
        reservation_id = SaleRepository(conn).get(sale_id).inventory_reservation_id

        result = CancelSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, reason="cliente se fue", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success
        assert result.data["sale"].status == "CANCELLED"
        row = conn.execute("SELECT estado FROM stock_reservas WHERE id=?",
                           (reservation_id,)).fetchone()
        assert row == ("cancelada",)
        assert SaleRepository(conn).get(sale_id).inventory_reservation_id is None
