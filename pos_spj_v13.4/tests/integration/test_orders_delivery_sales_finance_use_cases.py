"""ORD-22 — ProjectOrderToSaleUseCase/RecordOrderPaymentUseCase/
ReverseCustomerOrderUseCase, end-to-end against real SQLite with BOTH the
orders_delivery schema and the real Sales schema (master prompt §22:
Pedidos never writes `sales`/`sale_lines` directly — this proves the
cross-context calls actually create/pay/reverse a real `Sale`).

Full real pipeline: capture -> confirm -> reserve -> prepare -> mark ready
for pickup -> PROJECT TO SALE -> RECORD PAYMENT (fully, via the real Sales
flow) -> complete pickup -> REVERSE/REFUND. This replaces the raw
``UPDATE customer_orders SET payment_status='PAID'`` ORD-14's own tests used
as a stand-in for "a future Caja integration" — this phase IS that
integration.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.pickup_use_cases import (
    CompletePickupUseCase,
    MarkReadyForPickupUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
    CompletePreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.application.orders_delivery.use_cases.sales_finance_use_cases import (
    ProjectOrderToSaleUseCase,
    RecordOrderPaymentUseCase,
    ReverseCustomerOrderUseCase,
)
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-23: `MarkReadyForPickupUseCase` now fires a best-effort WhatsApp
    notification — keeps this ORD-22 pipeline helper network-free."""

    def notify_ready_for_pickup(self, **_kwargs) -> bool:
        return False


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_inventory_schema(connection)
    create_sales_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _sales_allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _seed_balance(conn, *, product_id: str, branch_id: str) -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','100','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _ready_pickup_order(conn) -> tuple[str, str]:
    """Returns (order_id, branch_id) for an order that has completed
    preparation and is ready for `MarkReadyForPickupUseCase` — same helper
    shape as ORD-14's own test, one line at 10.00 x 1."""
    branch_id, product_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ReserveOrderInventoryUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    AssignPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, assigned_to_user_id=new_uuid(),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    StartPreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
    RecordPreparedLineUseCase(_allow_all()).execute(
        conn, order_id=order_id, line_id=line_id, quantity="1",
        actor_user_id=new_uuid(), operation_id=new_uuid())
    CompletePreparationUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, branch_id


def _project(conn, order_id: str) -> str:
    result = ProjectOrderToSaleUseCase(_allow_all()).execute(
        conn, order_id=order_id, cashier_user_id=new_uuid(), actor_user_id=new_uuid(),
        operation_id=new_uuid(), sales_authorization=_sales_allow_all())
    assert result.success, result.message
    return result.data["sale_id"]


class TestProjectOrderToSaleUseCase:
    def test_projects_order_lines_onto_a_real_sale(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        sale_id = _project(conn, order_id)

        row = conn.execute("SELECT id, branch_id, status FROM sales WHERE id=?",
                            (sale_id,)).fetchone()
        assert row is not None
        line_rows = conn.execute(
            "SELECT product_id, quantity, unit_price FROM sale_lines WHERE sale_id=?",
            (sale_id,)).fetchall()
        assert len(line_rows) == 1

        order = CustomerOrderRepository(conn).get(order_id)
        assert order.sale_id == sale_id

    def test_is_idempotent_on_retry_without_duplicating_lines(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        operation_id = new_uuid()
        cashier_user_id, actor_user_id = new_uuid(), new_uuid()

        first = ProjectOrderToSaleUseCase(_allow_all()).execute(
            conn, order_id=order_id, cashier_user_id=cashier_user_id, actor_user_id=actor_user_id,
            operation_id=operation_id, sales_authorization=_sales_allow_all())
        second = ProjectOrderToSaleUseCase(_allow_all()).execute(
            conn, order_id=order_id, cashier_user_id=cashier_user_id, actor_user_id=actor_user_id,
            operation_id=operation_id, sales_authorization=_sales_allow_all())

        assert first.success and second.success
        assert first.data["sale_id"] == second.data["sale_id"]
        line_rows = conn.execute(
            "SELECT id FROM sale_lines WHERE sale_id=?", (first.data["sale_id"],)).fetchall()
        assert len(line_rows) == 1

    def test_fails_before_order_is_confirmed(self, conn):
        result_create = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=new_uuid(), channel="POS", order_type="STANDARD",
            fulfillment_type="COUNTER",
            lines=[{"product_id": new_uuid(), "unit_price": "10.00", "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())

        result = ProjectOrderToSaleUseCase(_allow_all()).execute(
            conn, order_id=result_create.entity_id, cashier_user_id=new_uuid(),
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            sales_authorization=_sales_allow_all())
        assert not result.success
        assert result.error_code == "CONFIRMATION_REQUIRED"


class TestRecordOrderPaymentUseCase:
    def test_full_payment_marks_paid_and_completes_the_sale(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        sale_id = _project(conn, order_id)
        order = CustomerOrderRepository(conn).get(order_id)
        total = order.totals.grand_total

        result = RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount=total, actor_user_id=new_uuid(),
            operation_id=new_uuid(), sales_authorization=_sales_allow_all())

        assert result.success
        assert result.data["payment_status"] == "PAID"
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.payment_status.value == "PAID"
        sale_row = conn.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()
        assert sale_row[0] == "COMPLETED"

    def test_partial_payment_marks_partially_paid_without_completing_sale(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        sale_id = _project(conn, order_id)
        order = CustomerOrderRepository(conn).get(order_id)
        partial = order.totals.grand_total / 2

        result = RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount=partial, actor_user_id=new_uuid(),
            operation_id=new_uuid(), sales_authorization=_sales_allow_all())

        assert result.success
        assert result.data["payment_status"] == "PARTIALLY_PAID"
        sale_row = conn.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()
        assert sale_row[0] != "COMPLETED"

    def test_fails_when_order_not_projected_to_sale(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        result = RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount="10.00", actor_user_id=new_uuid(),
            operation_id=new_uuid(), sales_authorization=_sales_allow_all())
        assert not result.success
        assert result.error_code == "ORDER_NOT_LINKED_TO_SALE"

    def test_retry_with_same_operation_id_does_not_double_charge(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        _project(conn, order_id)
        order = CustomerOrderRepository(conn).get(order_id)
        total = order.totals.grand_total
        operation_id = new_uuid()
        actor_user_id = new_uuid()

        first = RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount=total, actor_user_id=actor_user_id,
            operation_id=operation_id, sales_authorization=_sales_allow_all())
        second = RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount=total, actor_user_id=actor_user_id,
            operation_id=operation_id, sales_authorization=_sales_allow_all())

        assert first.success and second.success
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.payment_status.value == "PAID"
        sale_id = order.sale_id
        payment_rows = conn.execute(
            "SELECT id FROM sale_payments WHERE sale_id=?", (sale_id,)).fetchall()
        assert len(payment_rows) == 1


class TestReverseCustomerOrderUseCase:
    def _completed_paid_order(self, conn) -> tuple[str, str]:
        order_id, branch_id = _ready_pickup_order(conn)
        sale_id = _project(conn, order_id)
        order = CustomerOrderRepository(conn).get(order_id)
        RecordOrderPaymentUseCase(_allow_all()).execute(
            conn, order_id=order_id, method="CASH", amount=order.totals.grand_total,
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            sales_authorization=_sales_allow_all())
        order = CustomerOrderRepository(conn).get(order_id)
        CompletePickupUseCase(_allow_all()).execute(
            conn, order_id=order_id, presented_code=order.pickup_verification_code,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.status.value == "COMPLETED"
        return order_id, sale_id

    def test_reverses_order_and_sale_together(self, conn):
        order_id, sale_id = self._completed_paid_order(conn)

        result = ReverseCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, reason="Cliente reportó producto dañado",
            actor_user_id=new_uuid(), authorizer_user_id=new_uuid(), operation_id=new_uuid(),
            sales_authorization=_sales_allow_all())

        assert result.success, result.message
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.status.value == "REVERSED"
        assert order.payment_status.value == "REFUNDED"
        sale_row = conn.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()
        assert sale_row[0] == "REVERSED"

    def test_requires_distinct_authorizer(self, conn):
        order_id, _ = self._completed_paid_order(conn)
        same_user = new_uuid()

        result = ReverseCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, reason="Motivo", actor_user_id=same_user,
            authorizer_user_id=same_user, operation_id=new_uuid(),
            sales_authorization=_sales_allow_all())

        assert not result.success
        assert result.error_code == "SEGREGATION_OF_DUTIES"

    def test_rejects_refund_before_order_completed(self, conn):
        order_id, _ = _ready_pickup_order(conn)
        _project(conn, order_id)

        result = ReverseCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, reason="Motivo", actor_user_id=new_uuid(),
            authorizer_user_id=new_uuid(), operation_id=new_uuid(),
            sales_authorization=_sales_allow_all())

        assert not result.success
        assert result.error_code == "REFUND_NOT_ALLOWED"

    def test_retry_with_same_operation_id_does_not_double_refund(self, conn):
        order_id, sale_id = self._completed_paid_order(conn)
        operation_id = new_uuid()
        actor_user_id, authorizer_user_id = new_uuid(), new_uuid()

        first = ReverseCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, reason="Motivo", actor_user_id=actor_user_id,
            authorizer_user_id=authorizer_user_id, operation_id=operation_id,
            sales_authorization=_sales_allow_all())
        second = ReverseCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, reason="Motivo", actor_user_id=actor_user_id,
            authorizer_user_id=authorizer_user_id, operation_id=operation_id,
            sales_authorization=_sales_allow_all())

        assert first.success and second.success
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.status.value == "REVERSED"
