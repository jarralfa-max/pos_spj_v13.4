"""ORD-15 — CreateDeliveryJobUseCase/AssignDriverUseCase, end-to-end against
real SQLite, including idempotency by operation_id (§18's dedup pattern
reused for the new aggregate)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    AssignDriverUseCase,
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
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


def _confirmed_delivery_order(conn) -> tuple[str, str]:
    branch_id = new_uuid()
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
        lines=[{"product_id": new_uuid(), "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    return order_id, branch_id


class TestCreateDeliveryJobUseCase:
    def test_creates_job(self, conn):
        order_id, branch_id = _confirmed_delivery_order(conn)
        result = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["delivery_job"].status == "PENDING_ASSIGNMENT"
        assert result.data["delivery_job"].order_id == order_id

    def test_retry_same_operation_id_is_idempotent(self, conn):
        order_id, branch_id = _confirmed_delivery_order(conn)
        operation_id = new_uuid()
        first = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=operation_id)
        second = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=operation_id)
        assert first.entity_id == second.entity_id
        count = conn.execute("SELECT COUNT(*) FROM delivery_jobs").fetchone()[0]
        assert count == 1

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        order_id, branch_id = _confirmed_delivery_order(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = CreateDeliveryJobUseCase(policy).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_enqueues_job_created_event(self, conn):
        order_id, branch_id = _confirmed_delivery_order(conn)
        result = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (result.entity_id, "DELIVERY_JOB_CREATED")).fetchone()
        assert row is not None


class TestAssignDriverUseCase:
    def test_assigns_driver(self, conn):
        order_id, branch_id = _confirmed_delivery_order(conn)
        job_result = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        driver_id = new_uuid()
        result = AssignDriverUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_result.entity_id, driver_id=driver_id,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["delivery_job"].status == "ASSIGNED"
        reloaded = DeliveryJobRepository(conn).get(job_result.entity_id)
        assert reloaded.assigned_driver_id == driver_id

    def test_unknown_job_fails(self, conn):
        result = AssignDriverUseCase(_allow_all()).execute(
            conn, delivery_job_id=new_uuid(), driver_id=new_uuid(),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DELIVERY_JOB_NOT_FOUND"
