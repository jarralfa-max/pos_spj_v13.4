"""SALES-16/POS-16 — Cancelaciones y devoluciones: Cancel (already covered
by `test_sales_domain.py`/`test_sales_use_cases.py` — pre-payment only,
SALES-6), Return, Reverse, Authorization, Tests.

Inventory-restoration tests build the REAL canonical inventory schema
(`backend.infrastructure.db.schema.inventory_schema.create_inventory_schema`)
and verify actual stock increases via
`InventoryAvailabilityQueryService` — same precedent as
`tests/integration/inventory/test_inventory_adjustments.py` — proving
`ReturnSaleLineUseCase`/`ReverseSaleUseCase` compose into the real canonical
ledger, not a stand-in.
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.return_use_cases import ReturnSaleLineUseCase, ReverseSaleUseCase
from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import PaymentMethod, SaleStatus
from backend.domain.sales.exceptions import (
    ReturnQuantityExceededError,
    SaleReturnNotAllowedError,
    SaleReversalNotAllowedError,
)
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


# ── Domain ───────────────────────────────────────────────────────────────

def _completed_sale_entity(*, price="100.00", quantity="2") -> Sale:
    sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
    sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal(quantity)),
                  unit_price=Decimal(price))
    sale.begin_checkout()
    sale.record_payment(method=PaymentMethod.CASH, amount=sale.totals.total,
                        captured_by_user_id=new_uuid())
    sale.complete()
    return sale


class TestSaleReturnDomain:
    def test_return_requires_completed_or_partially_returned_status(self):
        sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("10"))
        with pytest.raises(SaleReturnNotAllowedError):
            sale.return_line(line_id=sale.lines[0].id, quantity=Decimal("1"), reason="motivo",
                             requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())

    def test_partial_return_transitions_to_returned_partially(self):
        sale = _completed_sale_entity(price="50.00", quantity="4")
        line = sale.lines[0]
        sale.return_line(line_id=line.id, quantity=Decimal("1"), reason="dañado",
                         requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())
        assert sale.status is SaleStatus.RETURNED_PARTIALLY

    def test_returning_everything_transitions_to_returned_fully(self):
        sale = _completed_sale_entity(price="50.00", quantity="2")
        line = sale.lines[0]
        sale.return_line(line_id=line.id, quantity=Decimal("2"), reason="no le gustó",
                         requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())
        assert sale.status is SaleStatus.RETURNED_FULLY

    def test_second_partial_return_completing_the_line_reaches_returned_fully(self):
        sale = _completed_sale_entity(price="50.00", quantity="3")
        line = sale.lines[0]
        r1 = sale.return_line(line_id=line.id, quantity=Decimal("1"), reason="motivo1",
                              requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())
        assert sale.status is SaleStatus.RETURNED_PARTIALLY
        r2 = sale.return_line(line_id=line.id, quantity=Decimal("2"), reason="motivo2",
                              requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())
        assert sale.status is SaleStatus.RETURNED_FULLY
        assert r1.id != r2.id

    def test_over_return_is_rejected(self):
        sale = _completed_sale_entity(price="50.00", quantity="2")
        line = sale.lines[0]
        with pytest.raises(ReturnQuantityExceededError):
            sale.return_line(line_id=line.id, quantity=Decimal("3"), reason="motivo",
                             requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())

    def test_return_amount_is_proportional_to_line_value(self):
        sale = _completed_sale_entity(price="30.00", quantity="4")  # line_total = 120.00
        line = sale.lines[0]
        result = sale.return_line(line_id=line.id, quantity=Decimal("1"), reason="motivo",
                                  requested_by_user_id=new_uuid(), authorized_by_user_id=new_uuid())
        assert result.amount == Decimal("30.00")


class TestSaleReverseDomain:
    def test_reverse_requires_completed_status(self):
        sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
        with pytest.raises(SaleReversalNotAllowedError):
            sale.reverse("motivo")

    def test_reverse_requires_a_reason(self):
        sale = _completed_sale_entity()
        with pytest.raises(SaleReversalNotAllowedError):
            sale.reverse("")

    def test_reverse_transitions_and_stamps_reversed_at(self):
        sale = _completed_sale_entity()
        sale.reverse("venta duplicada por error")
        assert sale.status is SaleStatus.REVERSED
        assert sale.reversed_at is not None

    def test_cannot_reverse_twice(self):
        sale = _completed_sale_entity()
        sale.reverse("motivo")
        with pytest.raises(SaleReversalNotAllowedError):
            sale.reverse("motivo otra vez")


# ── Application use cases ────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _completed_sale(conn, *, price="100.00", quantity="2"):
    branch, cashier = new_uuid(), new_uuid()
    product_id = new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=product_id, quantity=Decimal(quantity),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    sale = SaleRepository(conn).get(sale_id)
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method="CASH", amount=sale.totals.total,
        actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    line_id = SaleRepository(conn).get(sale_id).lines[0].id
    return sale_id, cashier, branch, product_id, line_id


class TestReturnSaleLineUseCase:
    def test_requires_return_permission(self, conn):
        sale_id, cashier, _branch, _product, line_id = _completed_sale(conn)
        from backend.application.sales.authorization import DenyAllSalesPermissionCheckerForTests

        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = ReturnSaleLineUseCase(denied).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="motivo",
            actor_user_id=cashier, authorizer_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_authorizer_must_be_a_distinct_user(self, conn):
        sale_id, cashier, _branch, _product, line_id = _completed_sale(conn)
        result = ReturnSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="motivo",
            actor_user_id=cashier, authorizer_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_restores_real_inventory_and_completes_line(self, conn):
        sale_id, cashier, branch, product_id, line_id = _completed_sale(
            conn, price="25.00", quantity="3")
        manager = new_uuid()

        result = ReturnSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="dañado",
            actor_user_id=cashier, authorizer_user_id=manager, operation_id=new_uuid())

        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.RETURNED_PARTIALLY
        assert len(sale.returns) == 1
        assert sale.returns[0].authorized_by_user_id == manager

        available = InventoryAvailabilityQueryService(conn).get_availability(
            product_id=product_id, branch_id=branch).available
        assert available == Decimal("1")

    def test_over_quantity_fails_without_touching_inventory(self, conn):
        sale_id, cashier, branch, product_id, line_id = _completed_sale(
            conn, price="10.00", quantity="1")
        result = ReturnSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("5"), reason="motivo",
            actor_user_id=cashier, authorizer_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "RETURN_QUANTITY_EXCEEDED"
        available = InventoryAvailabilityQueryService(conn).get_availability(
            product_id=product_id, branch_id=branch).available
        assert available == Decimal("0")

    def test_emits_returned_event(self, conn):
        sale_id, cashier, _branch, _product, line_id = _completed_sale(conn)
        ReturnSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="motivo",
            actor_user_id=cashier, authorizer_user_id=new_uuid(), operation_id=new_uuid())
        event = conn.execute(
            "SELECT event_name FROM sales_outbox WHERE event_name='SALE_RETURNED'"
            " AND payload_json LIKE ?", (f'%"entity_id": "{sale_id}"%',)).fetchone()
        assert event is not None


class TestReverseSaleUseCase:
    def test_requires_reverse_permission(self, conn):
        sale_id, cashier, _branch, _product, _line = _completed_sale(conn)
        from backend.application.sales.authorization import DenyAllSalesPermissionCheckerForTests

        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = ReverseSaleUseCase(denied).execute(
            conn, sale_id=sale_id, reason="motivo", actor_user_id=cashier,
            authorizer_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_authorizer_must_be_a_distinct_user(self, conn):
        sale_id, cashier, _branch, _product, _line = _completed_sale(conn)
        result = ReverseSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, reason="motivo", actor_user_id=cashier,
            authorizer_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_reverses_sale_and_restores_full_inventory(self, conn):
        sale_id, cashier, branch, product_id, _line = _completed_sale(
            conn, price="40.00", quantity="3")
        manager = new_uuid()

        result = ReverseSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, reason="venta duplicada", actor_user_id=cashier,
            authorizer_user_id=manager, operation_id=new_uuid())

        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.REVERSED
        assert sale.reversed_at is not None

        available = InventoryAvailabilityQueryService(conn).get_availability(
            product_id=product_id, branch_id=branch).available
        assert available == Decimal("3")

    def test_cash_effects_error_is_captured_without_blocking_reversal(self, conn):
        """No Caja shift schema exists in this fixture — the same honest,
        best-effort limit `CheckoutSaleUseCase` already documents (SALES-14):
        the reversal still succeeds even though the cash ledger side effect
        can't be composed atomically and has nothing real to reverse here."""
        sale_id, cashier, _branch, _product, _line = _completed_sale(conn)
        result = ReverseSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, reason="motivo", actor_user_id=cashier,
            authorizer_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success is True
        assert SaleRepository(conn).get(sale_id).status is SaleStatus.REVERSED
