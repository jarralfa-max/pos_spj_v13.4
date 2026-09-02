"""ORD-19 — RequestRedeliveryUseCase/ApproveRedeliveryUseCase/
ReturnToBranchUseCase, end-to-end through the real pipeline up through a
failed delivery attempt."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.dispatch_use_cases import (
    ConfirmArrivalUseCase,
    DispatchDeliveryJobUseCase,
    MarkInTransitUseCase,
    RecordDeliveryAttemptUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    AcceptAssignmentUseCase,
    ProposeAssignmentUseCase,
    RegisterDriverProfileUseCase,
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
    CompletePreparationUseCase,
    RecordPreparedLineUseCase,
    StartPreparationUseCase,
)
from backend.application.orders_delivery.use_cases.redelivery_use_cases import (
    ApproveRedeliveryUseCase,
    RejectRedeliveryUseCase,
    RequestRedeliveryUseCase,
    ReturnToBranchUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.redelivery_repository import (
    RedeliveryRequestRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-26: keeps this ORD-19-era test network-free — see the identical
    stub in test_orders_delivery_dispatch_use_cases.py."""

    def send_message(self, **_kwargs) -> bool:
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


def _failed_delivery_job(conn) -> str:
    branch_id, product_id, driver_id = new_uuid(), new_uuid(), new_uuid()
    _seed_balance(conn, product_id=product_id, branch_id=branch_id)

    result = CreateCustomerOrderUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
        fulfillment_type="HOME_DELIVERY",
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

    job_result = CreateDeliveryJobUseCase(_allow_all()).execute(
        conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    job_id = job_result.entity_id
    RegisterDriverProfileUseCase(_allow_all()).execute(
        conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    propose = ProposeAssignmentUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    AcceptAssignmentUseCase(_allow_all()).execute(
        conn, assignment_id=propose.entity_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
        conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    MarkInTransitUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    ConfirmArrivalUseCase(_allow_all()).execute(
        conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
    RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
        conn, delivery_job_id=job_id, successful=False, actor_user_id=new_uuid(),
        operation_id=new_uuid(), failure_reason="CUSTOMER_NOT_HOME")
    return job_id


class TestRequestRedeliveryUseCase:
    def test_requests_and_updates_job_status(self, conn):
        job_id = _failed_delivery_job(conn)
        result = RequestRedeliveryUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, reason="Cliente pidió reprogramar",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.status.value == "REDELIVERY_PENDING"

    def test_cannot_request_from_non_failed_job(self, conn):
        branch_id, product_id = new_uuid(), new_uuid()
        _seed_balance(conn, product_id=product_id, branch_id=branch_id)
        result = CreateCustomerOrderUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, channel="WHATSAPP", order_type="STANDARD",
            fulfillment_type="HOME_DELIVERY",
            lines=[{"product_id": product_id, "unit_price": "10.00", "requested_quantity": "1"}],
            actor_user_id=new_uuid(), operation_id=new_uuid())
        order_id = result.entity_id
        ConfirmCustomerOrderUseCase(_allow_all()).execute(
            conn, order_id=order_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        job_result = CreateDeliveryJobUseCase(_allow_all()).execute(
            conn, order_id=order_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = RequestRedeliveryUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_result.entity_id, reason="motivo",
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REDELIVERY_NOT_ALLOWED"


class TestApproveRedeliveryUseCase:
    def test_approve_creates_new_job(self, conn):
        job_id = _failed_delivery_job(conn)
        request_result = RequestRedeliveryUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, reason="motivo", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = ApproveRedeliveryUseCase(_allow_all()).execute(
            conn, redelivery_request_id=request_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        new_job_id = result.entity_id
        assert new_job_id != job_id
        new_job = DeliveryJobRepository(conn).get(new_job_id)
        assert new_job.status.value == "PENDING_ASSIGNMENT"
        request = RedeliveryRequestRepository(conn).get(request_result.entity_id)
        assert request.status.value == "APPROVED"
        assert request.new_delivery_job_id == new_job_id

    def test_reject_redelivery(self, conn):
        job_id = _failed_delivery_job(conn)
        request_result = RequestRedeliveryUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, reason="motivo", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = RejectRedeliveryUseCase(_allow_all()).execute(
            conn, redelivery_request_id=request_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        request = RedeliveryRequestRepository(conn).get(request_result.entity_id)
        assert request.status.value == "REJECTED"


class TestReturnToBranchUseCase:
    def test_returns_job_to_branch(self, conn):
        job_id = _failed_delivery_job(conn)
        result = ReturnToBranchUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.status.value == "RETURNED_TO_BRANCH"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        job_id = _failed_delivery_job(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = ReturnToBranchUseCase(policy).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
