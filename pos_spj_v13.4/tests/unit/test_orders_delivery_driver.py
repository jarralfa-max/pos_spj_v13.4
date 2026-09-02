"""ORD-16 — DriverOperationalProfile, DeliveryAssignment,
DriverAssignmentPolicy (§33-34)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.driver import DeliveryAssignment, DriverOperationalProfile
from backend.domain.orders_delivery.enums import AssignmentStatus
from backend.domain.orders_delivery.exceptions import (
    DriverNotAvailableError,
    InvalidAssignmentStateError,
)
from backend.domain.orders_delivery.policies.driver_assignment_policy import DriverAssignmentPolicy
from backend.shared.ids import new_uuid


class TestDriverOperationalProfile:
    def test_has_capacity_when_active_and_under_limit(self):
        profile = DriverOperationalProfile.create(
            driver_id=new_uuid(), branch_id=new_uuid(), capacity=2)
        assert profile.has_capacity

    def test_no_capacity_when_at_limit(self):
        profile = DriverOperationalProfile.create(
            driver_id=new_uuid(), branch_id=new_uuid(), capacity=1)
        profile.increment_assignments()
        assert not profile.has_capacity

    def test_no_capacity_when_inactive(self):
        profile = DriverOperationalProfile.create(driver_id=new_uuid(), branch_id=new_uuid())
        profile.deactivate()
        assert not profile.has_capacity

    def test_decrement_never_goes_negative(self):
        profile = DriverOperationalProfile.create(driver_id=new_uuid(), branch_id=new_uuid())
        profile.decrement_assignments()
        assert profile.current_assignment_count == 0


class TestDriverAssignmentPolicy:
    def test_rejects_inactive_driver(self):
        profile = DriverOperationalProfile.create(driver_id=new_uuid(), branch_id=new_uuid())
        profile.deactivate()
        with pytest.raises(DriverNotAvailableError):
            DriverAssignmentPolicy.ensure_can_assign(profile)

    def test_rejects_driver_at_capacity(self):
        profile = DriverOperationalProfile.create(
            driver_id=new_uuid(), branch_id=new_uuid(), capacity=1)
        profile.increment_assignments()
        with pytest.raises(DriverNotAvailableError):
            DriverAssignmentPolicy.ensure_can_assign(profile)

    def test_allows_active_driver_with_capacity(self):
        profile = DriverOperationalProfile.create(driver_id=new_uuid(), branch_id=new_uuid())
        DriverAssignmentPolicy.ensure_can_assign(profile)  # does not raise


class TestDeliveryAssignment:
    def test_accept_from_proposed(self):
        assignment = DeliveryAssignment.create(
            delivery_job_id=new_uuid(), driver_id=new_uuid(), assigned_by_user_id=new_uuid())
        assignment.accept()
        assert assignment.status == AssignmentStatus.ACCEPTED
        assert assignment.accepted_at is not None

    def test_reject_from_proposed(self):
        assignment = DeliveryAssignment.create(
            delivery_job_id=new_uuid(), driver_id=new_uuid(), assigned_by_user_id=new_uuid())
        assignment.reject()
        assert assignment.status == AssignmentStatus.REJECTED

    def test_cannot_accept_twice(self):
        assignment = DeliveryAssignment.create(
            delivery_job_id=new_uuid(), driver_id=new_uuid(), assigned_by_user_id=new_uuid())
        assignment.accept()
        with pytest.raises(InvalidAssignmentStateError):
            assignment.accept()

    def test_full_lifecycle(self):
        assignment = DeliveryAssignment.create(
            delivery_job_id=new_uuid(), driver_id=new_uuid(), assigned_by_user_id=new_uuid())
        assignment.accept()
        assignment.activate()
        assignment.complete()
        assert assignment.status == AssignmentStatus.COMPLETED
        assert assignment.released_at is not None

    def test_cannot_cancel_completed(self):
        assignment = DeliveryAssignment.create(
            delivery_job_id=new_uuid(), driver_id=new_uuid(), assigned_by_user_id=new_uuid())
        assignment.accept()
        assignment.activate()
        assignment.complete()
        with pytest.raises(InvalidAssignmentStateError):
            assignment.cancel()
