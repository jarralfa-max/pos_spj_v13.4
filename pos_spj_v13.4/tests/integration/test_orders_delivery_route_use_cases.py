"""ORD-17 — CreateRouteUseCase/AddStopToRouteUseCase/PlanRouteUseCase,
end-to-end against real SQLite, including DeliveryJob.route_id sync."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.orders_delivery.authorization import OrdersDeliveryAuthorizationPolicy
from backend.application.orders_delivery.use_cases.delivery_job_use_cases import (
    CreateDeliveryJobUseCase,
)
from backend.application.orders_delivery.use_cases.order_capture_use_cases import (
    ConfirmCustomerOrderUseCase,
    CreateCustomerOrderUseCase,
)
from backend.application.orders_delivery.use_cases.route_use_cases import (
    AddStopToRouteUseCase,
    CreateRouteUseCase,
    PlanRouteUseCase,
)
from backend.infrastructure.db.repositories.orders_delivery.delivery_job_repository import (
    DeliveryJobRepository,
)
from backend.infrastructure.db.repositories.orders_delivery.route_repository import (
    DeliveryRouteRepository,
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


class TestRoutePipeline:
    def test_create_add_stops_and_plan(self, conn):
        branch_id = new_uuid()
        job1, job2 = _delivery_job(conn, branch_id), _delivery_job(conn, branch_id)

        route_result = CreateRouteUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert route_result.success
        route_id = route_result.entity_id

        AddStopToRouteUseCase(_allow_all()).execute(
            conn, route_id=route_id, delivery_job_id=job1, sequence=1,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        stop2 = AddStopToRouteUseCase(_allow_all()).execute(
            conn, route_id=route_id, delivery_job_id=job2, sequence=2,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert stop2.success
        assert stop2.data["stop_count"] == 2

        job1_reloaded = DeliveryJobRepository(conn).get(job1)
        assert job1_reloaded.route_id == route_id

        plan_result = PlanRouteUseCase(_allow_all()).execute(
            conn, route_id=route_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        assert plan_result.success
        route = DeliveryRouteRepository(conn).get(route_id)
        assert route.status.value == "PLANNED"
        assert [s.delivery_job_id for s in route.ordered_stops] == [job1, job2]

    def test_plan_without_stops_fails(self, conn):
        branch_id = new_uuid()
        route_result = CreateRouteUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, actor_user_id=new_uuid(), operation_id=new_uuid())
        result = PlanRouteUseCase(_allow_all()).execute(
            conn, route_id=route_result.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INVALID_ROUTE_STOP"

    def test_add_stop_to_unknown_route_fails(self, conn):
        branch_id = new_uuid()
        job_id = _delivery_job(conn, branch_id)
        result = AddStopToRouteUseCase(_allow_all()).execute(
            conn, route_id=new_uuid(), delivery_job_id=job_id, sequence=1,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "ROUTE_NOT_FOUND"

    def test_denies_without_permission(self, conn):
        from backend.application.orders_delivery.authorization import (
            DenyAllOrdersDeliveryPermissionCheckerForTests,
        )
        policy = OrdersDeliveryAuthorizationPolicy(DenyAllOrdersDeliveryPermissionCheckerForTests())
        result = CreateRouteUseCase(policy).execute(
            conn, branch_id=new_uuid(), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
