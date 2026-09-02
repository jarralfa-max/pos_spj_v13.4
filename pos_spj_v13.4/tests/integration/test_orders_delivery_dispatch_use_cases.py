"""ORD-18 — DispatchDeliveryJobUseCase/MarkInTransitUseCase/
ConfirmArrivalUseCase/RecordDeliveryAttemptUseCase, end-to-end through the
FULL real pipeline: capture -> confirm -> reserve -> assign/start/record/
complete preparation -> create job -> register+propose+accept driver ->
dispatch -> transit -> arrive -> deliver."""

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
from backend.infrastructure.db.repositories.orders_delivery.customer_order_repository import (
    CustomerOrderRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _NoOpWhatsAppClient:
    """ORD-26: `DispatchDeliveryJobUseCase`/`RecordDeliveryAttemptUseCase` now
    fire best-effort WhatsApp notifications — keeps this ORD-18-era test
    network-free, same stub shape as
    test_orders_delivery_customer_notification_use_cases.py."""

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


def _dispatch_ready_job(conn) -> tuple[str, str, str]:
    """Returns (delivery_job_id, order_id, driver_id) for a job that has an
    ACCEPTED driver assignment and an order that just finished preparation —
    i.e. everything DispatchPolicy requires, built through the real
    use cases from every earlier ORD phase."""
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
    return job_id, order_id, driver_id


class TestDispatchDeliveryJobUseCase:
    def test_dispatches_and_updates_both_aggregates(self, conn):
        job_id, order_id, _ = _dispatch_ready_job(conn)
        result = DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.status.value == "DISPATCHED"
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.fulfillment_status.value == "DISPATCHED"

    def test_dispatch_without_driver_fails(self, conn):
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
        result = DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DISPATCH_NOT_ALLOWED"


class TestFullDeliveryPipeline:
    def test_successful_delivery_completes_order(self, conn):
        job_id, order_id, _ = _dispatch_ready_job(conn)
        DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        MarkInTransitUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ConfirmArrivalUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, successful=True, actor_user_id=new_uuid(),
            operation_id=new_uuid(), recipient_name="Ana", pin_verified=True)
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.status.value == "DELIVERED"
        assert len(job.attempts) == 1
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.status.value == "COMPLETED"
        assert order.fulfillment_status.value == "DELIVERED"

    def test_failed_delivery_does_not_complete_order(self, conn):
        job_id, order_id, _ = _dispatch_ready_job(conn)
        DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        MarkInTransitUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ConfirmArrivalUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, successful=False, actor_user_id=new_uuid(),
            operation_id=new_uuid(), failure_reason="CUSTOMER_NOT_HOME")
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.status.value == "FAILED"
        order = CustomerOrderRepository(conn).get(order_id)
        assert order.status.value != "COMPLETED"

    def test_successful_attempt_without_evidence_fails(self, conn):
        job_id, _, _ = _dispatch_ready_job(conn)
        DispatchDeliveryJobUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        MarkInTransitUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        ConfirmArrivalUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RecordDeliveryAttemptUseCase(_allow_all(), whatsapp_client=_NoOpWhatsAppClient()).execute(
            conn, delivery_job_id=job_id, successful=True, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DELIVERY_EVIDENCE_REQUIRED"

    def test_denies_dispatch_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        job_id, _, _ = _dispatch_ready_job(conn)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = DispatchDeliveryJobUseCase(policy).execute(
            conn, delivery_job_id=job_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
