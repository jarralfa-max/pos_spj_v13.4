"""ORD-14 — MarkReadyForPickupUseCase/CompletePickupUseCase, end-to-end
through the full real pipeline: capture -> confirm -> reserve -> assign ->
start -> record prepared -> complete preparation -> mark ready -> pay ->
complete pickup."""

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
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-23: `MarkReadyForPickupUseCase` now fires a best-effort WhatsApp
    notification — keeps this ORD-14-era test network-free."""

    def notify_ready_for_pickup(self, **_kwargs) -> bool:
        return False


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    create_inventory_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _seed_balance(conn, *, product_id: str, branch_id: str) -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','100','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _ready_pickup_order(conn) -> str:
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
    return order_id


class TestMarkReadyForPickupUseCase:
    def test_generates_and_persists_verification_code(self, conn):
        order_id = _ready_pickup_order(conn)
        result = MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert len(result.data["verification_code"]) == 6
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.pickup_verification_code == result.data["verification_code"]


class TestCompletePickupUseCase:
    def test_completes_with_correct_code_and_payment(self, conn):
        order_id = _ready_pickup_order(conn)
        ready = MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        code = ready.data["verification_code"]

        # Payment collection is out of this bounded context's scope (§47) —
        # tests set payment_status directly, same as a future Caja
        # integration would after collecting payment.
        conn.execute("UPDATE customer_orders SET payment_status='PAID' WHERE id=?", (order_id,))

        result = CompletePickupUseCase(_allow_all()).execute(
            conn, order_id=order_id, presented_code=code, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.status.value == "COMPLETED"
        assert reloaded.fulfillment_status.value == "DELIVERED"

    def test_wrong_code_fails(self, conn):
        order_id = _ready_pickup_order(conn)
        MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        conn.execute("UPDATE customer_orders SET payment_status='PAID' WHERE id=?", (order_id,))
        result = CompletePickupUseCase(_allow_all()).execute(
            conn, order_id=order_id, presented_code="000000", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PICKUP_VERIFICATION_FAILED"

    def test_unpaid_order_fails(self, conn):
        order_id = _ready_pickup_order(conn)
        ready = MarkReadyForPickupUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = CompletePickupUseCase(_allow_all()).execute(
            conn, order_id=order_id, presented_code=ready.data["verification_code"],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PAYMENT_REQUIRED"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id = _ready_pickup_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = CompletePickupUseCase(policy).execute(
            conn, order_id=order_id, presented_code="000000", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
