"""ORD-9 — AssignPreparationUseCase/StartPreparationUseCase/
RecordPreparedLineUseCase/CompletePreparationUseCase, end-to-end through the
full pipeline built so far: capture -> confirm -> reserve -> prepare."""

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
        " VALUES (?,?,?,?,'','','','AVAILABLE','100','0','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, "t"))


def _reserved_order(conn) -> tuple[str, str]:
    branch_id, product_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "2"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ReserveOrderInventoryUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, product_id


class TestPreparationPipeline:
    def test_full_happy_path(self, conn):
        order_id, _ = _reserved_order(conn)

        assign = AssignPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, assigned_to_user_id=new_uuid(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert assign.success

        start = StartPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert start.success

        line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id
        record = RecordPreparedLineUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, quantity="2",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert record.success

        complete = CompletePreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert complete.success
        assert complete.data["order"].fulfillment_status == "READY"

    def test_cannot_complete_with_unprepared_lines(self, conn):
        order_id, _ = _reserved_order(conn)
        AssignPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, assigned_to_user_id=new_uuid(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        StartPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = CompletePreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PREPARATION_NOT_ALLOWED"

    def test_record_unknown_line_fails(self, conn):
        order_id, _ = _reserved_order(conn)
        result = RecordPreparedLineUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=new_uuid(), quantity="1",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "LINE_NOT_FOUND"

    def test_denies_start_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id, _ = _reserved_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = StartPreparationUseCase(policy).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_start_enqueues_preparation_started_event(self, conn):
        order_id, _ = _reserved_order(conn)
        AssignPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, assigned_to_user_id=new_uuid(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        StartPreparationUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_PREPARATION_STARTED")).fetchone()
        assert row is not None
