"""ORD-8 — ReserveOrderInventoryUseCase/ReleaseOrderInventoryUseCase,
end-to-end against real SQLite with BOTH the orders_delivery schema and the
real, already-migrated Inventory schema (master prompt §23-24: Pedidos never
writes Inventory's tables directly — this proves the cross-context call
actually reserves/releases against Inventory's own `inventory_balances`).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReleaseOrderInventoryUseCase,
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
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


def _seed_balance(conn, *, product_id: str, branch_id: str, quantity: str = "100") -> None:
    conn.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
        " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
        " reserved_quantity, reserved_weight, version, updated_at)"
        " VALUES (?,?,?,?,'','','','AVAILABLE',?,'0','0','0',0,?)",
        (new_uuid(), product_id, branch_id, branch_id, quantity, "t"))


def _create_confirmed_order(conn, *, branch_id: str, product_id: str) -> str:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "5"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=result.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return result.entity_id


class TestReserveOrderInventoryUseCase:
    def test_reserves_stock_for_every_line(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)

        result = ReserveOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert result.success
        assert result.data["order"].fulfillment_status == "RESERVED"
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].inventory_reservation_id is not None
        row = conn.execute(
            "SELECT reserved_quantity FROM inventory_balances WHERE product_id=?",
            (product_id,)).fetchone()
        assert row[0] == "5"

    def test_fails_when_insufficient_stock(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id, quantity="1")
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)

        result = ReserveOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        assert not result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.fulfillment_status == "FAILED"
        assert reloaded.lines[0].inventory_reservation_id is None

    def test_fails_when_no_balance_exists(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)
        result = ReserveOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVENTORY_RESERVATION_FAILED"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = ReserveOrderInventoryUseCase(policy).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_enqueues_reserved_event(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)
        ReserveOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_RESERVED")).fetchone()
        assert row is not None


class TestReleaseOrderInventoryUseCase:
    def test_releases_reserved_stock(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)
        ReserveOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())

        result = ReleaseOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            reason="Pedido cancelado")

        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.lines[0].inventory_reservation_id is None
        row = conn.execute(
            "SELECT reserved_quantity FROM inventory_balances WHERE product_id=?",
            (product_id,)).fetchone()
        assert row[0] == "0"

    def test_release_without_reservation_is_a_no_op(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        order_id = _create_confirmed_order(conn, branch_id=branch_id, product_id=product_id)
        result = ReleaseOrderInventoryUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
