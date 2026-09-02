"""ORD-16 — RegisterDriverProfileUseCase/ProposeAssignmentUseCase/
AcceptAssignmentUseCase/RejectAssignmentUseCase, end-to-end against real
SQLite, including capacity enforcement and DeliveryJob.assigned_driver_id
sync on acceptance."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.driver_use_cases import (
    AcceptAssignmentUseCase,
    ProposeAssignmentUseCase,
    RegisterDriverProfileUseCase,
    RejectAssignmentUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.driver_repository import (
    DriverOperationalProfileRepository,
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


def _delivery_job(conn, branch_id: str) -> str:
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
        operation_id=new_uuid())
    return job_result.entity_id


class TestRegisterDriverProfileUseCase:
    def test_registers_profile(self, conn):
        driver_id = new_uuid()
        result = RegisterDriverProfileUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=new_uuid(), actor_user_id=new_uuid(),
            operation_id=new_uuid(), capacity=3)
        assert result.success
        profile = DriverOperationalProfileRepository(conn).get_by_driver_id(driver_id)
        assert profile.capacity == 3


class TestProposeAcceptRejectAssignment:
    def test_propose_requires_existing_profile(self, conn):
        branch_id = new_uuid()
        job_id = _delivery_job(conn, branch_id)
        result = ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, driver_id=new_uuid(), actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DRIVER_PROFILE_NOT_FOUND"

    def test_propose_rejects_driver_at_capacity(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        RegisterDriverProfileUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid(), capacity=1)
        job1, job2 = _delivery_job(conn, branch_id), _delivery_job(conn, branch_id)
        ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job1, driver_id=driver_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job2, driver_id=driver_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "DRIVER_NOT_AVAILABLE"

    def test_accept_syncs_delivery_job_driver(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        RegisterDriverProfileUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        job_id = _delivery_job(conn, branch_id)
        propose = ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job_id, driver_id=driver_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        result = AcceptAssignmentUseCase(_allow_all()).execute(
            conn, assignment_id=propose.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        job = DeliveryJobRepository(conn).get(job_id)
        assert job.assigned_driver_id == driver_id
        assert job.status.value == "ASSIGNED"

    def test_reject_frees_up_capacity(self, conn):
        branch_id, driver_id = new_uuid(), new_uuid()
        RegisterDriverProfileUseCase(_allow_all()).execute(
            conn, driver_id=driver_id, branch_id=branch_id, actor_user_id=new_uuid(),
            operation_id=new_uuid(), capacity=1)
        job1 = _delivery_job(conn, branch_id)
        propose = ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job1, driver_id=driver_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        RejectAssignmentUseCase(_allow_all()).execute(
            conn, assignment_id=propose.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        profile = DriverOperationalProfileRepository(conn).get_by_driver_id(driver_id)
        assert profile.current_assignment_count == 0
        # Capacity freed: a second proposal for a new job succeeds.
        job2 = _delivery_job(conn, branch_id)
        result = ProposeAssignmentUseCase(_allow_all()).execute(
            conn, delivery_job_id=job2, driver_id=driver_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        branch_id = new_uuid()
        job_id = _delivery_job(conn, branch_id)
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = ProposeAssignmentUseCase(policy).execute(
            conn, delivery_job_id=job_id, driver_id=new_uuid(), actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
