"""ORD-19 — FailureReason validation, RedeliveryRequest lifecycle,
DeliveryJob.request_redelivery()/start_return()/complete_return() (§40-41)."""

from __future__ import annotations

import pytest

from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.enums import DeliveryStatus, RedeliveryStatus
from backend.domain.orders_delivery.exceptions import (
    DeliveryFailureReasonRequiredError,
    InvalidRedeliveryStateError,
)
from backend.domain.orders_delivery.redelivery import RedeliveryRequest
from backend.shared.ids import new_uuid


class TestFailureReasonValidation:
    def test_rejects_unknown_failure_reason(self):
        with pytest.raises(DeliveryFailureReasonRequiredError):
            DeliveryAttempt.create(
                delivery_job_id=new_uuid(), successful=False, failure_reason="NOT_A_REAL_REASON")

    def test_accepts_catalog_reason(self):
        attempt = DeliveryAttempt.create(
            delivery_job_id=new_uuid(), successful=False, failure_reason="WRONG_ADDRESS")
        assert attempt.failure_reason == "WRONG_ADDRESS"


def _failed_job() -> DeliveryJob:
    job = DeliveryJob.create(order_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())
    job.assign_driver(driver_id=new_uuid())
    job.mark_ready_to_dispatch()
    job.dispatch()
    job.mark_in_transit()
    job.mark_arrived()
    job.start_delivery_attempt()
    job.record_attempt(DeliveryAttempt.create(
        delivery_job_id=job.id, successful=False, failure_reason="CUSTOMER_NOT_HOME"))
    return job


class TestDeliveryJobFailureFlows:
    def test_request_redelivery_from_failed(self):
        job = _failed_job()
        job.request_redelivery()
        assert job.status == DeliveryStatus.REDELIVERY_PENDING

    def test_return_to_branch_flow(self):
        job = _failed_job()
        job.start_return()
        assert job.status == DeliveryStatus.RETURNING
        job.complete_return()
        assert job.status == DeliveryStatus.RETURNED_TO_BRANCH


class TestRedeliveryRequest:
    def test_create_requires_reason(self):
        with pytest.raises(InvalidRedeliveryStateError):
            RedeliveryRequest.create(
                original_delivery_job_id=new_uuid(), reason="  ",
                requested_by_user_id=new_uuid())

    def test_approve_sets_new_job(self):
        request = RedeliveryRequest.create(
            original_delivery_job_id=new_uuid(), reason="Cliente no localizable",
            requested_by_user_id=new_uuid())
        new_job_id = new_uuid()
        request.approve(approved_by_user_id=new_uuid(), new_delivery_job_id=new_job_id)
        assert request.status == RedeliveryStatus.APPROVED
        assert request.new_delivery_job_id == new_job_id

    def test_cannot_approve_twice(self):
        request = RedeliveryRequest.create(
            original_delivery_job_id=new_uuid(), reason="motivo",
            requested_by_user_id=new_uuid())
        request.approve(approved_by_user_id=new_uuid(), new_delivery_job_id=new_uuid())
        with pytest.raises(InvalidRedeliveryStateError):
            request.approve(approved_by_user_id=new_uuid(), new_delivery_job_id=new_uuid())

    def test_reject_from_pending(self):
        request = RedeliveryRequest.create(
            original_delivery_job_id=new_uuid(), reason="motivo",
            requested_by_user_id=new_uuid())
        request.reject()
        assert request.status == RedeliveryStatus.REJECTED

    def test_complete_requires_approved(self):
        request = RedeliveryRequest.create(
            original_delivery_job_id=new_uuid(), reason="motivo",
            requested_by_user_id=new_uuid())
        with pytest.raises(InvalidRedeliveryStateError):
            request.complete()
