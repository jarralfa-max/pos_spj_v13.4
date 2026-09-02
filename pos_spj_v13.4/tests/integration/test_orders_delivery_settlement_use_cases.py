"""ORD-21 — CreateDriverSettlementUseCase/ApproveDriverSettlementUseCase/
CloseDriverSettlementUseCase, end-to-end against real SQLite, including
marking every included collection SETTLED."""

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
from backend.application.orders_delivery.use_cases.settlement_use_cases import (
    ApproveDriverSettlementUseCase,
    CloseDriverSettlementUseCase,
    CreateDriverSettlementUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.cash_collection_repository import (
    DriverCashCollectionRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.settlement_repository import (
    DriverSettlementRepository,
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


def _pending_settlement_collection(conn, *, branch_id: str, driver_id: str,
                                    cash_to_collect: str, collected: str) -> str:
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
        operation_id=new_uuid(), cash_to_collect=Decimal(cash_to_collect),
        payment_method_expected="CASH")
    job_id = job_result.entity_id
    AssignDriverUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    collection_result = CreateCashCollectionRequestUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, payment_method="CASH", actor_user_id=new_uuid(),
        operation_id=new_uuid())
    RecordCashCollectionUseCase(_allow_all()).execute(
        conn, collection_id=collection_result.entity_id, collected_amount=Decimal(collected),
        actor_user_id=new_uuid(), operation_id=new_uuid())
    conn.execute(
        "UPDATE driver_cash_collections SET status='PENDING_SETTLEMENT' WHERE id=?",
        (collection_result.entity_id,))
    return collection_result.entity_id


class TestCreateDriverSettlementUseCase:
    def test_creates_balanced_settlement(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        _pending_settlement_collection(
            conn, branch_id=branch_id, driver_id=driver_id, cash_to_collect="100.00",
            collected="100.00")
        result = CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["status"] == "BALANCED"
        assert result.data["difference"] == Decimal("0")

    def test_creates_settlement_with_difference(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        _pending_settlement_collection(
            conn, branch_id=branch_id, driver_id=driver_id, cash_to_collect="100.00",
            collected="80.00")
        result = CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["status"] == "WITH_DIFFERENCE"

    def test_marks_collections_settled(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        collection_id = _pending_settlement_collection(
            conn, branch_id=branch_id, driver_id=driver_id, cash_to_collect="100.00",
            collected="100.00")
        CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        collection = DriverCashCollectionRepository(conn).get(collection_id)
        assert collection.status.value == "SETTLED"

    def test_fails_with_no_pending_collections(self, conn):
        result = CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=new_uuid(), branch_id=new_uuid(), actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SETTLEMENT_REQUIRES_COLLECTIONS"


class TestApproveAndCloseSettlement:
    def test_approve_balanced_and_close(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        _pending_settlement_collection(
            conn, branch_id=branch_id, driver_id=driver_id, cash_to_collect="100.00",
            collected="100.00")
        create_result = CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        approve_result = ApproveDriverSettlementUseCase(_allow_all()).execute(
            conn, settlement_id=create_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert approve_result.data["status"] == "APPROVED"
        close_result = CloseDriverSettlementUseCase(_allow_all()).execute(
            conn, settlement_id=create_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert close_result.success
        settlement = DriverSettlementRepository(conn).get(create_result.entity_id)
        assert settlement.status.value == "CLOSED"

    def test_with_difference_goes_to_pending_review_first(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        _pending_settlement_collection(
            conn, branch_id=branch_id, driver_id=driver_id, cash_to_collect="100.00",
            collected="80.00")
        create_result = CreateDriverSettlementUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        approve_result = ApproveDriverSettlementUseCase(_allow_all()).execute(
            conn, settlement_id=create_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert approve_result.data["status"] == "PENDING_REVIEW"

    def test_settlement_not_found(self, conn):
        result = ApproveDriverSettlementUseCase(_allow_all()).execute(
            conn, settlement_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SETTLEMENT_NOT_FOUND"
