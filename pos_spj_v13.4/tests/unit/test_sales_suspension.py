"""SALES-15/POS-15 — Suspensiones: Persist, Resume, Expire, Counter, Tests.

Persist/Resume already exist (SALES-6/9) — the coverage here is Expire
(a genuine new gap: SALES-9's `ExpireOrphanedInventoryReservationsUseCase`
only releases the INVENTORY side of a stale suspension, never the Sale
itself) and Counter (a lightweight badge count, matching the real legacy
`modulos/ventas.py::ventas_en_espera` Reanudar-button precedent), plus a
short round-trip regression for Persist/Resume so this phase's own test
file is a complete POS-15 record, not just the two new pieces.

Inventory fixtures reuse the exact hand-rolled `stock_reservas`/
`stock_reserva_detalles`/`inventory_stock` DDL from
`test_sales_inventory_reservation.py` (SALES-9).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.queries.sale_query_service import SaleQueryService
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.inventory_use_cases import ReserveInventoryForSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import ResumeSaleUseCase, SuspendSaleUseCase
from backend.application.sales.use_cases.suspension_sweep_use_cases import ExpireSuspendedSalesUseCase
from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SalesPermissionDeniedError
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    c.execute("CREATE TABLE inventory_stock (branch_id TEXT, product_id TEXT, quantity REAL)")
    c.execute("""
        CREATE TABLE stock_reservas (
            id TEXT NOT NULL PRIMARY KEY, folio TEXT UNIQUE, branch_id TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activa', payload_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT (datetime('now', '+30 minutes'))
        )
    """)
    c.execute("""
        CREATE TABLE stock_reserva_detalles (
            id TEXT NOT NULL PRIMARY KEY, reserva_id TEXT NOT NULL REFERENCES stock_reservas(id),
            producto_id TEXT NOT NULL, cantidad REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


def _seed_stock(conn, *, branch_id: str, product_id: str, quantity: float) -> None:
    conn.execute("INSERT INTO inventory_stock (branch_id, product_id, quantity) VALUES (?,?,?)",
                 (branch_id, product_id, quantity))
    conn.commit()


def _suspend_a_sale(conn, *, branch_id=None):
    """`SuspendSaleUseCase` always reserves inventory as part of suspending
    (SALES-9's real behavior, matching legacy `suspender_venta`) — stock
    must always be seeded, not conditionally."""
    branch_id = branch_id or new_uuid()
    cashier = new_uuid()
    product_id = new_uuid()
    _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10)
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
        unit_price=Decimal("50.00"), actor_user_id=cashier, operation_id=new_uuid())
    result = SuspendSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
        max_suspended_sales=5)
    assert result.success, result.message
    return sale_id, cashier, branch_id


def _backdate_suspension(conn, sale_id: str, *, hours_ago: float) -> None:
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    conn.execute("UPDATE sales SET suspended_at=? WHERE id=?", (stamp, sale_id))
    conn.commit()


# ── Persist / Resume (short regression, full coverage lives in SALES-9's own suite) ──

class TestPersistAndResume:
    def test_suspended_sale_round_trips_through_the_repository(self, conn):
        sale_id, cashier, branch = _suspend_a_sale(conn)
        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.SUSPENDED
        assert sale.suspended_at is not None
        assert sale.suspended_by_user_id == cashier

    def test_resume_transitions_back_to_active(self, conn):
        sale_id, cashier, _branch = _suspend_a_sale(conn)
        result = ResumeSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.ACTIVE
        assert sale.suspended_at is None


# ── Expire ────────────────────────────────────────────────────────────────

class TestExpireSuspendedSalesUseCase:
    def test_expires_old_suspended_sale_and_cancels_it(self, conn):
        sale_id, _cashier, _branch = _suspend_a_sale(conn)
        _backdate_suspension(conn, sale_id, hours_ago=5)

        expired_count = ExpireSuspendedSalesUseCase().execute(conn, max_age_hours=4)

        assert expired_count == 1
        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.CANCELLED
        assert sale.cancelled_at is not None

    def test_releases_inventory_reservation_on_expiry(self, conn):
        sale_id, cashier, branch = _suspend_a_sale(conn)
        assert SaleRepository(conn).get(sale_id).inventory_reservation_id is not None
        _backdate_suspension(conn, sale_id, hours_ago=5)

        ExpireSuspendedSalesUseCase().execute(conn, max_age_hours=4)

        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.CANCELLED
        assert sale.inventory_reservation_id is None
        reserva = conn.execute(
            "SELECT estado FROM stock_reservas WHERE branch_id=?", (branch,)).fetchone()
        assert reserva["estado"] != "activa"

    def test_does_not_expire_recently_suspended_sales(self, conn):
        sale_id, _cashier, _branch = _suspend_a_sale(conn)
        expired_count = ExpireSuspendedSalesUseCase().execute(conn, max_age_hours=4)
        assert expired_count == 0
        assert SaleRepository(conn).get(sale_id).status is SaleStatus.SUSPENDED

    def test_expiry_emits_cancelled_event_to_outbox(self, conn):
        sale_id, _cashier, _branch = _suspend_a_sale(conn)
        _backdate_suspension(conn, sale_id, hours_ago=10)
        ExpireSuspendedSalesUseCase().execute(conn, max_age_hours=4)
        event = conn.execute(
            "SELECT event_name, payload_json FROM sales_outbox"
            " WHERE event_name='SALE_CANCELLED' AND payload_json LIKE ?",
            (f'%"entity_id": "{sale_id}"%',)).fetchone()
        assert event is not None
        assert '"expired": true' in event["payload_json"]

    def test_sweeps_multiple_branches_in_one_call(self, conn):
        sale_a, _c1, _b1 = _suspend_a_sale(conn)
        sale_b, _c2, _b2 = _suspend_a_sale(conn)
        _backdate_suspension(conn, sale_a, hours_ago=10)
        _backdate_suspension(conn, sale_b, hours_ago=10)
        expired_count = ExpireSuspendedSalesUseCase().execute(conn, max_age_hours=4)
        assert expired_count == 2


# ── Counter ──────────────────────────────────────────────────────────────

class TestSuspendedCounter:
    def test_counts_zero_with_no_suspended_sales(self, conn):
        service = SaleQueryService(conn, _allow_all())
        assert service.count_suspended(branch_id=new_uuid(), requester_user_id=new_uuid()) == 0

    def test_counts_suspended_sales_for_branch(self, conn):
        branch = new_uuid()
        _suspend_a_sale(conn, branch_id=branch)
        _suspend_a_sale(conn, branch_id=branch)
        _suspend_a_sale(conn)  # different branch — must not leak into the count

        service = SaleQueryService(conn, _allow_all())
        assert service.count_suspended(branch_id=branch, requester_user_id=new_uuid()) == 2

    def test_count_decreases_after_resume(self, conn):
        branch = new_uuid()
        sale_id, cashier, _branch = _suspend_a_sale(conn, branch_id=branch)
        service = SaleQueryService(conn, _allow_all())
        assert service.count_suspended(branch_id=branch, requester_user_id=new_uuid()) == 1

        ResumeSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert service.count_suspended(branch_id=branch, requester_user_id=new_uuid()) == 0

    def test_requires_view_permission(self, conn):
        service = SaleQueryService(conn, SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests()))
        with pytest.raises(SalesPermissionDeniedError):
            service.count_suspended(branch_id=new_uuid(), requester_user_id=new_uuid())
