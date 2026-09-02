"""ORD-11 — ExpireCustomerApprovalUseCase end-to-end through the full
pipeline: capture -> confirm -> reserve -> assign -> start -> record
prepared -> evaluate (out of tolerance) -> expire."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.catch_weight_use_cases import (
    EvaluateCatchWeightUseCase,
    ExpireCustomerApprovalUseCase,
)
from backend.application.orders_delivery.use_cases.inventory_use_cases import (
    ReserveOrderInventoryUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.preparation_use_cases import (
    AssignPreparationUseCase,
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
    """ORD-23: keeps this ORD-11-era test network-free — see the identical
    stub in test_orders_delivery_catch_weight_use_cases.py."""

    def notify_customer_approval_required(self, **_kwargs) -> bool:
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


def _pending_approval_order(conn, *, expires_at: str) -> str:
    branch_id, product_id = new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="POS", order_type="STANDARD",
        fulfillment_type="COUNTER",
        lines=[{
            "product_id": product_id, "unit_price": "100.00",
            "requested_weight": "2.000", "requested_weight_unit": "KG",
            "catch_weight_enabled": True,
        }], actor_user_id=new_uuid(), operation_id=new_uuid())
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
        conn, order_id=order_id, line_id=line_id, weight="2.600",
        actor_user_id=new_uuid(), operation_id=new_uuid())
    EvaluateCatchWeightUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
        conn, order_id=order_id, line_id=line_id, tolerance_pct=Decimal("5"),
        actor_user_id=new_uuid(), operation_id=new_uuid(), approval_expires_at=expires_at)
    return order_id


class TestExpireCustomerApprovalUseCase:
    def test_expires_and_rejects_pending_line(self, conn):
        now = datetime.now(timezone.utc)
        expires_at = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
        order_id = _pending_approval_order(conn, expires_at=expires_at)

        result = ExpireCustomerApprovalUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)

        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.customer_approval_status.value == "EXPIRED"
        assert reloaded.lines[0].status.value == "REJECTED"

    def test_expire_not_due_fails(self, conn):
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
        order_id = _pending_approval_order(conn, expires_at=expires_at)

        result = ExpireCustomerApprovalUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)

        assert not result.success
        assert result.error_code == "APPROVAL_EXPIRATION_NOT_DUE"

    def test_accept_after_expiration_via_use_case_fails(self, conn):
        from backend.application.orders_delivery.use_cases.catch_weight_use_cases import (
            AcceptWeightAdjustmentUseCase,
        )
        now = datetime.now(timezone.utc)
        expires_at = (now - timedelta(minutes=5)).isoformat(timespec="seconds")
        order_id = _pending_approval_order(conn, expires_at=expires_at)
        ExpireCustomerApprovalUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)
        line_id = CustomerOrderRepository(conn).get(order_id).lines[0].id

        result = AcceptWeightAdjustmentUseCase(_allow_all()).execute(
            conn, order_id=order_id, line_id=line_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())

        assert not result.success
        assert result.error_code == "CUSTOMER_APPROVAL_EXPIRED"
