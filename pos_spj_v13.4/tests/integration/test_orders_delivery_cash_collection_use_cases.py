"""ORD-20 — CreateCashCollectionRequestUseCase/RecordCashCollectionUseCase,
end-to-end against real SQLite, including idempotent request creation and
the driver-assigned precondition."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.cash_collection_use_cases import (
    CreateCashCollectionRequestUseCase,
    RecordCashCollectionUseCase,
)
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    AssignDriverUseCase,
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.cash_collection_repository import (
    DriverCashCollectionRepository,
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


def _job_with_driver(conn, *, cash_to_collect: Decimal = Decimal("250.00")) -> tuple[str, str]:
    branch_id = new_uuid()
    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
        lines=[{"product_id": new_uuid(), "unit_price": "10.00", "requested_quantity": "1"}],
        actor_user_id=new_uuid(), operation_id=new_uuid())
    order_id = result.entity_id
    ConfirmCustomerOrderUseCase(_allow_all()).execute(
        conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    job_result = CreateDeliveryJobUseCase(_allow_all()).execute(
        conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid(), cash_to_collect=cash_to_collect,
        payment_method_expected="CASH")
    job_id = job_result.entity_id
    driver_id = new_uuid()
    AssignDriverUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    return job_id, driver_id


class TestCreateCashCollectionRequestUseCase:
    def test_creates_request_with_expected_amount(self, conn):
        job_id, driver_id = _job_with_driver(conn)
        result = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        collection = DriverCashCollectionRepository(conn).get(result.entity_id)
        assert collection.expected_amount == Decimal("250.00")
        assert collection.driver_id == driver_id

    def test_retry_is_idempotent(self, conn):
        job_id, _ = _job_with_driver(conn)
        first = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        second = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert first.entity_id == second.entity_id
        count = conn.execute("SELECT COUNT(*) FROM driver_cash_collections").fetchone()[0]
        assert count == 1


class TestRecordCashCollectionUseCase:
    def test_records_full_payment(self, conn):
        job_id, _ = _job_with_driver(conn)
        request = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = RecordCashCollectionUseCase(_allow_all()).execute(
            conn, collection_id=request.entity_id, collected_amount=Decimal("250.00"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["status"] == "COLLECTED"

    def test_records_partial_payment(self, conn):
        job_id, _ = _job_with_driver(conn)
        request = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = RecordCashCollectionUseCase(_allow_all()).execute(
            conn, collection_id=request.entity_id, collected_amount=Decimal("100.00"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.data["status"] == "PARTIALLY_COLLECTED"

    def test_unknown_collection_fails(self, conn):
        result = RecordCashCollectionUseCase(_allow_all()).execute(
            conn, collection_id=new_uuid(), collected_amount=Decimal("100.00"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CASH_COLLECTION_NOT_FOUND"

    def test_enqueues_collection_recorded_event(self, conn):
        job_id, _ = _job_with_driver(conn)
        request = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        RecordCashCollectionUseCase(_allow_all()).execute(
            conn, collection_id=request.entity_id, collected_amount=Decimal("250.00"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        row = conn.execute(
            "SELECT 1 FROM orders_delivery_outbox WHERE aggregate_id=? AND event_type=?",
            (job_id, "DELIVERY_CASH_COLLECTION_RECORDED")).fetchone()
        assert row is not None

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        job_id, _ = _job_with_driver(conn)
        request = CreateCashCollectionRequestUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = RecordCashCollectionUseCase(policy).execute(
            conn, collection_id=request.entity_id, collected_amount=Decimal("250.00"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
