"""ORD-18 — DispatchPolicy, DeliveryEvidence, DeliveryAttempt,
DeliveryJob.record_attempt(), CustomerOrder.mark_dispatched()/
complete_delivery() (§36-40)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.delivery_job import DeliveryAttempt, DeliveryJob
from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    DeliveryStatus,
    FulfillmentStatus,
    FulfillmentType,
    OrderChannel,
    OrderStatus,
    OrderType,
)
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.exceptions import (
    DeliveryEvidenceRequiredError,
    DeliveryFailureReasonRequiredError,
    DispatchNotAllowedError,
    InvalidOrderStateError,
)
from backend.domain.orders_delivery.policies.dispatch_policy import DispatchPolicy
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


class TestDispatchPolicy:
    def test_requires_ready_fulfillment_status(self):
        with pytest.raises(DispatchNotAllowedError):
            DispatchPolicy.ensure_can_dispatch(
                fulfillment_status=FulfillmentStatus.PREPARING,
                customer_approval_status=CustomerApprovalStatus.NOT_REQUIRED,
                has_assigned_driver=True)

    def test_requires_no_pending_approval(self):
        with pytest.raises(DispatchNotAllowedError):
            DispatchPolicy.ensure_can_dispatch(
                fulfillment_status=FulfillmentStatus.READY,
                customer_approval_status=CustomerApprovalStatus.PENDING,
                has_assigned_driver=True)

    def test_requires_assigned_driver(self):
        with pytest.raises(DispatchNotAllowedError):
            DispatchPolicy.ensure_can_dispatch(
                fulfillment_status=FulfillmentStatus.READY,
                customer_approval_status=CustomerApprovalStatus.NOT_REQUIRED,
                has_assigned_driver=False)

    def test_allows_when_all_conditions_met(self):
        DispatchPolicy.ensure_can_dispatch(
            fulfillment_status=FulfillmentStatus.READY,
            customer_approval_status=CustomerApprovalStatus.NOT_REQUIRED,
            has_assigned_driver=True)  # does not raise


class TestDeliveryAttempt:
    def test_successful_attempt_requires_evidence(self):
        with pytest.raises(DeliveryEvidenceRequiredError):
            DeliveryAttempt.create(delivery_job_id=new_uuid(), successful=True)

    def test_successful_attempt_with_evidence(self):
        evidence = DeliveryEvidence(recipient_name="Juan", pin_verified=True)
        attempt = DeliveryAttempt.create(
            delivery_job_id=new_uuid(), successful=True, evidence=evidence)
        assert attempt.successful

    def test_failed_attempt_requires_reason(self):
        with pytest.raises(DeliveryFailureReasonRequiredError):
            DeliveryAttempt.create(delivery_job_id=new_uuid(), successful=False)

    def test_failed_attempt_with_reason(self):
        attempt = DeliveryAttempt.create(
            delivery_job_id=new_uuid(), successful=False, failure_reason="CUSTOMER_NOT_HOME")
        assert not attempt.successful


class TestDeliveryJobRecordAttempt:
    def _dispatched_job(self) -> DeliveryJob:
        job = DeliveryJob.create(order_id=new_uuid(), branch_id=new_uuid(), operation_id=new_uuid())
        job.assign_driver(driver_id=new_uuid())
        job.mark_ready_to_dispatch()
        job.dispatch()
        job.mark_in_transit()
        job.mark_arrived()
        job.start_delivery_attempt()
        return job

    def test_successful_attempt_marks_delivered(self):
        job = self._dispatched_job()
        attempt = DeliveryAttempt.create(
            delivery_job_id=job.id, successful=True,
            evidence=DeliveryEvidence(recipient_name="Juan"))
        job.record_attempt(attempt)
        assert job.status == DeliveryStatus.DELIVERED
        assert len(job.attempts) == 1

    def test_failed_attempt_marks_failed(self):
        job = self._dispatched_job()
        attempt = DeliveryAttempt.create(
            delivery_job_id=job.id, successful=False, failure_reason="CUSTOMER_NOT_HOME")
        job.record_attempt(attempt)
        assert job.status == DeliveryStatus.FAILED


class TestCustomerOrderDispatchDelivery:
    def _confirmed_delivery_order(self) -> CustomerOrder:
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.WHATSAPP, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.HOME_DELIVERY)
        order.add_line(CustomerOrderLine.create(
            order_id=order.id, product_id=new_uuid(), unit_price=Decimal("10"),
            requested_quantity=OrderQuantity(Decimal("1"))))
        order.confirm(confirmed_by_user_id=new_uuid())
        order.mark_reserved()
        order.fulfillment_status = FulfillmentStatus.READY  # ORD-9's own step
        return order

    def test_mark_dispatched(self):
        order = self._confirmed_delivery_order()
        order.mark_dispatched()
        assert order.fulfillment_status == FulfillmentStatus.DISPATCHED

    def test_complete_delivery_requires_dispatched(self):
        order = self._confirmed_delivery_order()
        with pytest.raises(InvalidOrderStateError):
            order.complete_delivery()

    def test_complete_delivery_succeeds_when_dispatched(self):
        order = self._confirmed_delivery_order()
        order.mark_dispatched()
        order.complete_delivery()
        assert order.status == OrderStatus.COMPLETED
        assert order.fulfillment_status == FulfillmentStatus.DELIVERED
