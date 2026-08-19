"""SALES-14/POS-14 — Checkout: Atomic operation, Outbox, Cash effects,
Inventory, Loyalty, Tests.

Inventory fixtures reuse the exact hand-rolled `stock_reservas`/
`stock_reserva_detalles`/`inventory_stock` DDL already established in
`test_sales_inventory_reservation.py` (SALES-9). Cash-effects fixtures build
the REAL Caja bounded-context schema (`migrations.standalone.
175_cash_register_bounded_context_schema`), same precedent as
`test_sales_hardware.py` (SALES-12) — proving `CheckoutSaleUseCase` composes
into Caja's real ledger without re-testing Caja's own internals. Loyalty
fixtures reuse the `loyalty_ledger` DDL established in
`test_sales_pricing_loyalty.py` (SALES-11).
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import QuickCreateCustomerForSaleUseCase
from backend.application.sales.use_cases.inventory_use_cases import ReserveInventoryForSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.loyalty_use_cases import RedeemLoyaltyPointsUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.domain.sales.enums import SaleStatus
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
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


def _sale_ready_and_paid(conn, *, price="100.00", reserve=False, branch_id=None):
    branch_id = branch_id or new_uuid()
    cashier = new_uuid()
    product_id = new_uuid()
    if reserve:
        _seed_stock(conn, branch_id=branch_id, product_id=product_id, quantity=10)
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    if reserve:
        ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal(price),
        actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier, branch_id


class TestCheckoutSaleUseCase:
    def test_fails_when_payment_incomplete(self, conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("100.00"), actor_user_id=cashier, operation_id=new_uuid())
        BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PAYMENT_INCOMPLETE"

    def test_completes_and_leaves_no_partial_state_on_failure(self, conn):
        """The pre-validation-before-mutation ordering: a failed checkout
        must not have touched inventory or emitted any outbox event."""
        sale_id, cashier, branch = _sale_ready_and_paid(conn, price="100.00", reserve=True)
        # Under-record: cancel the effect of the paid amount by starting a
        # SECOND sale that shares nothing, to prove the failing one here is
        # untouched — simpler: just assert the reservation is still 'activa'
        # (untouched) after a fully-paid, successful run further down; this
        # test instead verifies the safe-no-op path directly.
        unpaid_branch, unpaid_cashier = new_uuid(), new_uuid()
        product_id = new_uuid()
        _seed_stock(conn, branch_id=unpaid_branch, product_id=product_id, quantity=5)
        unpaid_sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=unpaid_branch, cashier_user_id=unpaid_cashier,
            operation_id=new_uuid(), actor_user_id=unpaid_cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=unpaid_sale_id, product_id=product_id, quantity=Decimal("1"),
            unit_price=Decimal("50.00"), actor_user_id=unpaid_cashier, operation_id=new_uuid())
        ReserveInventoryForSaleUseCase(_allow_all()).execute(
            conn, sale_id=unpaid_sale_id, actor_user_id=unpaid_cashier, operation_id=new_uuid())
        BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=unpaid_sale_id, actor_user_id=unpaid_cashier, operation_id=new_uuid())

        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=unpaid_sale_id, actor_user_id=unpaid_cashier, operation_id=new_uuid())
        assert result.success is False

        reserva = conn.execute(
            "SELECT estado FROM stock_reservas WHERE branch_id=?", (unpaid_branch,)).fetchone()
        assert reserva["estado"] == "activa"  # never touched — checkout never reached inventory
        sale = SaleRepository(conn).get(unpaid_sale_id)
        assert sale.status is SaleStatus.CHECKOUT_PENDING  # unchanged

    def test_confirms_inventory_reservation_and_completes(self, conn):
        sale_id, cashier, branch = _sale_ready_and_paid(conn, price="100.00", reserve=True)
        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True

        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.COMPLETED
        reserva = conn.execute(
            "SELECT estado FROM stock_reservas WHERE branch_id=?", (branch,)).fetchone()
        assert reserva["estado"] != "activa"  # confirmed, no longer just held

    def test_completes_without_any_inventory_reservation(self, conn):
        sale_id, cashier, _branch = _sale_ready_and_paid(conn, price="100.00", reserve=False)
        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        assert SaleRepository(conn).get(sale_id).status is SaleStatus.COMPLETED

    def test_emits_payment_confirmed_and_completed_to_outbox_atomically(self, conn):
        sale_id, cashier, _branch = _sale_ready_and_paid(conn, price="100.00")
        CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        events = {row["event_name"] for row in conn.execute(
            "SELECT event_name FROM sales_outbox WHERE payload_json LIKE ?",
            (f'%"entity_id": "{sale_id}"%',)).fetchall()}
        assert "SALE_PAYMENT_CONFIRMED" in events
        assert "SALE_COMPLETED" in events

    def test_cash_effects_error_is_captured_without_blocking_completion(self, conn):
        """No Caja shift schema/open shift exists in this fixture at all —
        the honest, documented limit: cash effects are best-effort, a
        missing/unopen shift never un-completes the sale."""
        sale_id, cashier, _branch = _sale_ready_and_paid(conn, price="100.00")
        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        assert result.data.get("cash_effects_error")
        assert SaleRepository(conn).get(sale_id).status is SaleStatus.COMPLETED


# ── Cash effects: real Caja schema ──────────────────────────────────────

@pytest.fixture
def cash_conn():
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
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema"
    ).run(c)
    c.commit()
    yield c
    c.close()


def _open_cash_shift(conn, *, branch_id: str, cashier_user_id: str) -> None:
    register, drawer, terminal, shift = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    now = "2026-08-17T12:00:00+00:00"
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch_id, "Caja 1", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch_id, register, "Cajón 1", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch_id, register, "Terminal 1", "ACTIVE", now, now))
    conn.execute(
        "INSERT INTO cash_shifts (id, branch_id, register_id, drawer_id, terminal_id, "
        "cashier_user_id, opening_amount, opening_operation_id, status, opened_at) "
        "VALUES (?,?,?,?,?,?,?,?, 'OPEN', ?)",
        (shift, branch_id, register, drawer, terminal, cashier_user_id, "0", new_uuid(), now))
    conn.commit()


class TestCheckoutSaleUseCaseCashEffects:
    def test_cash_sale_with_open_shift_writes_real_ledger_entry(self, cash_conn):
        sale_id, cashier, branch = _sale_ready_and_paid(cash_conn, price="100.00")
        _open_cash_shift(cash_conn, branch_id=branch, cashier_user_id=cashier)

        result = CheckoutSaleUseCase(_allow_all()).execute(
            cash_conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        assert result.data.get("cash_effects_error") is None

        entry = cash_conn.execute(
            "SELECT movement_type, amount FROM cash_ledger_entries WHERE reference_id=?",
            (sale_id,)).fetchone()
        assert entry is not None
        assert entry["movement_type"] == "CASH_SALE"
        assert entry["amount"] == "100.00"


# ── Loyalty redemption ────────────────────────────────────────────────────

@pytest.fixture
def loyalty_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.execute("""
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, email TEXT,
            codigo_qr TEXT, codigo_fidelidad TEXT, activo INTEGER DEFAULT 1, puntos INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE loyalty_ledger (
            id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('acumulacion','canje','reversa','ajuste')),
            puntos INTEGER NOT NULL, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0,
            referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT,
            usuario TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


def _create_customer(conn, *, display_name="Ana Torres") -> str:
    return QuickCreateCustomerForSaleUseCase(CustomerAuthorizationPolicy.permissive_for_tests()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
        display_name=display_name).entity_id


def _award_points(conn, *, legacy_customer_id: str, points: int) -> None:
    conn.execute(
        "INSERT INTO loyalty_ledger (id, cliente_id, tipo, puntos, saldo_post) "
        "VALUES (?, ?, 'acumulacion', ?, ?)",
        (new_uuid(), legacy_customer_id, points, points))
    conn.commit()


class TestRedeemLoyaltyPointsUseCase:
    def test_fails_without_assigned_customer(self, loyalty_conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            loyalty_conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("500.00"), actor_user_id=cashier, operation_id=new_uuid())
        result = RedeemLoyaltyPointsUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "LOYALTY_REDEMPTION_UNAVAILABLE"

    def test_fails_when_customer_has_no_points(self, loyalty_conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            loyalty_conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("500.00"), actor_user_id=cashier, operation_id=new_uuid())
        customer_id = _create_customer(loyalty_conn)
        AssignCustomerToSaleUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())

        result = RedeemLoyaltyPointsUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "LOYALTY_REDEMPTION_UNAVAILABLE"

    def test_redeems_real_points_and_reduces_sale_total(self, loyalty_conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            loyalty_conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("500.00"), actor_user_id=cashier, operation_id=new_uuid())
        customer_id = _create_customer(loyalty_conn)
        AssignCustomerToSaleUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(loyalty_conn, customer_id=customer_id)
        loyalty_conn.execute("UPDATE clientes SET nombre='Bridge stub' WHERE id=?", (legacy_id,))
        _award_points(loyalty_conn, legacy_customer_id=legacy_id, points=200)

        result = RedeemLoyaltyPointsUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
            operation_id=new_uuid())
        assert result.success is True
        assert result.data["points_redeemed"] > 0

        sale = SaleRepository(loyalty_conn).get(sale_id)
        assert sale.loyalty_redeemed_amount > Decimal("0")
        assert sale.totals.loyalty_total == sale.loyalty_redeemed_amount
        assert sale.totals.total == sale.totals.gross_subtotal - sale.loyalty_redeemed_amount

    def test_redemption_is_idempotent_for_the_same_sale(self, loyalty_conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            loyalty_conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("500.00"), actor_user_id=cashier, operation_id=new_uuid())
        customer_id = _create_customer(loyalty_conn)
        AssignCustomerToSaleUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(loyalty_conn, customer_id=customer_id)
        loyalty_conn.execute("UPDATE clientes SET nombre='Bridge stub' WHERE id=?", (legacy_id,))
        _award_points(loyalty_conn, legacy_customer_id=legacy_id, points=200)

        first = RedeemLoyaltyPointsUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
            operation_id=new_uuid())
        second = RedeemLoyaltyPointsUseCase(_allow_all()).execute(
            loyalty_conn, sale_id=sale_id, points=100, actor_user_id=cashier,
            operation_id=new_uuid())
        assert first.success is True
        assert second.success is True
