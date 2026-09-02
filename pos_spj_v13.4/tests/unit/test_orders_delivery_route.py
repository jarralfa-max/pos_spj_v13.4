"""ORD-17 — DeliveryRoute/DeliveryRouteStop (§35): stops, sequencing,
RoutePolicy transitions."""

from __future__ import annotations

import pytest

from backend.domain.orders_delivery.enums import RouteStatus
from backend.domain.orders_delivery.exceptions import InvalidRouteStateError, InvalidRouteStopError
from backend.domain.orders_delivery.route import DeliveryRoute
from backend.shared.ids import new_uuid


class TestAddStop:
    def test_add_stop_appends(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.add_stop(delivery_job_id=new_uuid(), sequence=1)
        assert len(route.stops) == 1

    def test_rejects_duplicate_sequence(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.add_stop(delivery_job_id=new_uuid(), sequence=1)
        with pytest.raises(InvalidRouteStopError):
            route.add_stop(delivery_job_id=new_uuid(), sequence=1)

    def test_rejects_zero_sequence(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        with pytest.raises(InvalidRouteStopError):
            route.add_stop(delivery_job_id=new_uuid(), sequence=0)

    def test_ordered_stops_sorts_by_sequence(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        job_a, job_b = new_uuid(), new_uuid()
        route.add_stop(delivery_job_id=job_a, sequence=2)
        route.add_stop(delivery_job_id=job_b, sequence=1)
        ordered = route.ordered_stops
        assert ordered[0].delivery_job_id == job_b
        assert ordered[1].delivery_job_id == job_a

    def test_cannot_add_stop_after_planned(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.add_stop(delivery_job_id=new_uuid(), sequence=1)
        route.plan()
        with pytest.raises(InvalidRouteStopError):
            route.add_stop(delivery_job_id=new_uuid(), sequence=2)


class TestRouteLifecycle:
    def test_cannot_plan_without_stops(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        with pytest.raises(InvalidRouteStopError):
            route.plan()

    def test_full_happy_path(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.add_stop(delivery_job_id=new_uuid(), sequence=1)
        route.plan()
        assert route.status == RouteStatus.PLANNED
        route.assign_driver(driver_id=new_uuid())
        assert route.status == RouteStatus.ASSIGNED
        route.activate()
        assert route.status == RouteStatus.ACTIVE
        route.complete()
        assert route.status == RouteStatus.COMPLETED

    def test_cannot_transition_final_route(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.add_stop(delivery_job_id=new_uuid(), sequence=1)
        route.plan()
        route.assign_driver(driver_id=new_uuid())
        route.activate()
        route.complete()
        with pytest.raises(InvalidRouteStateError):
            route.cancel()

    def test_cancel_from_draft(self):
        route = DeliveryRoute.create(branch_id=new_uuid())
        route.cancel()
        assert route.status == RouteStatus.CANCELLED
