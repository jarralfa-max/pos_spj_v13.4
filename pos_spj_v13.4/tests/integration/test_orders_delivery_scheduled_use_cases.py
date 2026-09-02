"""ORD-6 — ScheduleOrderUseCase/RescheduleOrderUseCase/
ActivateScheduledOrderUseCase, end-to-end against real SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.scheduled_order_use_cases import (
    ActivateScheduledOrderUseCase,
    RescheduleOrderUseCase,
    ScheduleOrderUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def _allow_all() -> OrdersDeliveryAuthorizationPolicy:
    return OrdersDeliveryAuthorizationPolicy.permissive_for_tests()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _create_order(conn) -> str:
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=new_uuid(), channel="WHATSAPP", order_type="SCHEDULED",
        fulfillment_type="SCHEDULED_DELIVERY",
        lines=[{"product_id": new_uuid(), "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    return result.entity_id


class TestScheduleOrderUseCase:
    def test_schedules_and_persists(self, conn):
        order_id = _create_order(conn)
        now = datetime.now(timezone.utc)
        result = ScheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=_iso(now + timedelta(days=1)),
            window_start=_iso(now + timedelta(days=1)),
            window_end=_iso(now + timedelta(days=1, hours=2)),
            activation_at=_iso(now + timedelta(hours=12)),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.schedule_status.value == "SCHEDULED"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id = _create_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        now = datetime.now(timezone.utc)
        result = ScheduleOrderUseCase(policy).execute(
            conn, order_id=order_id, scheduled_for=_iso(now), window_start=_iso(now),
            window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestActivateScheduledOrderUseCase:
    def test_activates_when_due(self, conn):
        order_id = _create_order(conn)
        now = datetime.now(timezone.utc)
        ScheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=_iso(now), window_start=_iso(now),
            window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now - timedelta(minutes=5)),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ActivateScheduledOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)
        assert result.success
        assert result.data["order"].status  # DTO round-trips fine

    def test_activation_not_due_fails(self, conn):
        order_id = _create_order(conn)
        now = datetime.now(timezone.utc)
        ScheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=_iso(now), window_start=_iso(now),
            window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now + timedelta(hours=2)),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = ActivateScheduledOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)
        assert not result.success
        assert result.error_code == "ACTIVATION_NOT_DUE"

    def test_activation_enqueues_outbox_event(self, conn):
        order_id = _create_order(conn)
        now = datetime.now(timezone.utc)
        ScheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=_iso(now), window_start=_iso(now),
            window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now - timedelta(minutes=5)),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        ActivateScheduledOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid(), now=now)
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (order_id, "ORDER_SCHEDULE_ACTIVATED")).fetchone()
        assert row is not None


class TestRescheduleOrderUseCase:
    def test_reschedule_changes_window(self, conn):
        order_id = _create_order(conn)
        now = datetime.now(timezone.utc)
        ScheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=_iso(now), window_start=_iso(now),
            window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        new_start = _iso(now + timedelta(days=3))
        result = RescheduleOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, scheduled_for=new_start, window_start=new_start,
            window_end=_iso(now + timedelta(days=3, hours=1)), activation_at=new_start,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        reloaded = CustomerOrderRepository(conn).get(order_id)
        assert reloaded.delivery_window_start == new_start
        assert reloaded.schedule_status.value == "RESCHEDULED"
