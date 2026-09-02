"""ORD-15 — DeliveryJob (§31-32): creation, driver assignment,
DeliveryLifecyclePolicy transitions, and the full lifecycle methods built
now for ORD-16-19 to reuse."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.delivery_job import DeliveryJob
from backend.domain.orders_delivery.enums import DeliveryStatus
from backend.domain.orders_delivery.exceptions import (
    DeliveryDriverRequiredError,
    InvalidDeliveryJobStateError,
)
from backend.shared.ids import new_uuid


def _job() -> DeliveryJob:
    return DeliveryJob.create(order_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())


class TestDeliveryJobCreation:
    def test_starts_pending_assignment(self):
        job = _job()
        assert job.status == DeliveryStatus.PENDING_ASSIGNMENT
        assert job.assigned_driver_id is None

    def test_carries_delivery_fee_and_cash_to_collect(self):
        job = DeliveryJob.create(
            order_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid(),
            delivery_fee=Decimal("35.00"), cash_to_collect=Decimal("250.00"))
        assert job.delivery_fee == Decimal("35.00")
        assert job.cash_to_collect == Decimal("250.00")


class TestAssignDriver:
    def test_assign_sets_status_and_driver(self):
        job = _job()
        driver_id = new_uuid()
        job.assign_driver(driver_id=driver_id)
        assert job.status == DeliveryStatus.ASSIGNED
        assert job.assigned_driver_id == driver_id

    def test_reassign_before_dispatch_is_allowed(self):
        job = _job()
        job.assign_driver(driver_id=new_uuid())
        new_driver = new_uuid()
        job.assign_driver(driver_id=new_driver)
        assert job.assigned_driver_id == new_driver

    def test_cannot_assign_after_dispatch(self):
        job = _job()
        job.assign_driver(driver_id=new_uuid())
        job.mark_ready_to_dispatch()
        job.dispatch()
        with pytest.raises(InvalidDeliveryJobStateError):
            job.assign_driver(driver_id=new_uuid())


class TestDispatchRequiresDriver:
    def test_dispatch_without_driver_raises(self):
        """Isolates `dispatch()`'s own driver-presence guard from the
        lifecycle policy by forcing the precondition status directly —
        reaching READY_TO_DISPATCH without a driver isn't reachable through
        the public API (`mark_ready_to_dispatch()` requires ASSIGNED
        first), but `dispatch()` must never assume that invariant silently
        held."""
        job = _job()
        job.status = DeliveryStatus.READY_TO_DISPATCH
        with pytest.raises(DeliveryDriverRequiredError):
            job.dispatch()

    def test_full_happy_path(self):
        job = _job()
        job.assign_driver(driver_id=new_uuid())
        job.mark_ready_to_dispatch()
        job.dispatch()
        assert job.status == DeliveryStatus.DISPATCHED
        assert job.dispatched_at is not None
        job.mark_in_transit()
        job.mark_arrived()
        job.start_delivery_attempt()
        job.mark_delivered()
        assert job.status == DeliveryStatus.DELIVERED
        assert job.delivered_at is not None
        job.close()
        assert job.status == DeliveryStatus.CLOSED

    def test_failed_delivery_can_go_to_redelivery(self):
        job = _job()
        job.assign_driver(driver_id=new_uuid())
        job.mark_ready_to_dispatch()
        job.dispatch()
        job.mark_in_transit()
        job.mark_arrived()
        job.start_delivery_attempt()
        job.mark_failed()
        assert job.status == DeliveryStatus.FAILED
        assert job.failed_at is not None


class TestFinalStatuses:
    def test_delivered_is_final_except_close(self):
        job = _job()
        job.assign_driver(driver_id=new_uuid())
        job.mark_ready_to_dispatch()
        job.dispatch()
        job.mark_in_transit()
        job.mark_arrived()
        job.start_delivery_attempt()
        job.mark_delivered()
        with pytest.raises(InvalidDeliveryJobStateError):
            job.assign_driver(driver_id=new_uuid())

    def test_cancel_from_pending_assignment(self):
        job = _job()
        job.cancel()
        assert job.status == DeliveryStatus.CANCELLED
