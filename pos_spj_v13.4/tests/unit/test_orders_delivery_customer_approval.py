"""ORD-11 — customer approval idempotency and expiration (§27): repeated
accept/reject is a no-op, an expired approval blocks further decisions, and
`expire_customer_approval()` treats a timed-out pending line as an implicit
rejection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderType,
)
from backend.domain.orders_delivery.exceptions import (
    ApprovalExpirationNotDueError,
    CustomerApprovalExpiredError,
    InvalidOrderStateError,
)
from backend.domain.orders_delivery.policies.catch_weight_adjustment_policy import (
    CatchWeightAdjustmentPolicy,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _order_with_pending_adjustment(*, expires_at: str | None = None):
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER)
    line = CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("100.00"),
        requested_weight=OrderQuantity(Decimal("2.000"), unit="KG"), catch_weight_enabled=True)
    order.add_line(line)
    line.record_prepared_amount(weight=OrderQuantity(Decimal("2.600"), unit="KG"))
    evaluation = CatchWeightAdjustmentPolicy.evaluate(
        requested_amount=Decimal("2.000"), prepared_amount=Decimal("2.600"),
        unit_price=Decimal("100"), tolerance_pct=Decimal("5"))
    order.apply_weight_evaluation(line_id=line.id, evaluation=evaluation,
                                  approval_expires_at=expires_at)
    return order, line


class TestIdempotency:
    def test_accepting_twice_is_a_no_op(self):
        order, line = _order_with_pending_adjustment()
        order.accept_customer_adjustment(line.id)
        order.accept_customer_adjustment(line.id)  # must not raise
        assert line.status == OrderLineStatus.PREPARED
        assert line.final_weight.value == Decimal("2.600")

    def test_rejecting_twice_is_a_no_op(self):
        order, line = _order_with_pending_adjustment()
        order.reject_customer_adjustment(line.id)
        order.reject_customer_adjustment(line.id)  # must not raise
        assert line.status == OrderLineStatus.REJECTED

    def test_accept_after_reject_is_a_real_conflict(self):
        order, line = _order_with_pending_adjustment()
        order.reject_customer_adjustment(line.id)
        with pytest.raises(InvalidOrderStateError):
            order.accept_customer_adjustment(line.id)


class TestExpiration:
    def test_expire_before_due_raises(self):
        now = datetime.now(timezone.utc)
        order, _ = _order_with_pending_adjustment(expires_at=_iso(now + timedelta(hours=1)))
        with pytest.raises(ApprovalExpirationNotDueError):
            order.expire_customer_approval(now=now)

    def test_expire_when_due_rejects_pending_lines(self):
        now = datetime.now(timezone.utc)
        order, line = _order_with_pending_adjustment(expires_at=_iso(now - timedelta(minutes=1)))
        order.expire_customer_approval(now=now)
        assert line.status == OrderLineStatus.REJECTED
        assert order.customer_approval_status == CustomerApprovalStatus.EXPIRED

    def test_expire_without_pending_approval_raises(self):
        order = CustomerOrder.create(
            branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
            fulfillment_type=FulfillmentType.COUNTER)
        with pytest.raises(InvalidOrderStateError):
            order.expire_customer_approval(now=datetime.now(timezone.utc))

    def test_accept_after_expiration_raises(self):
        now = datetime.now(timezone.utc)
        order, line = _order_with_pending_adjustment(expires_at=_iso(now - timedelta(minutes=1)))
        order.expire_customer_approval(now=now)
        with pytest.raises(CustomerApprovalExpiredError):
            order.accept_customer_adjustment(line.id)

    def test_reject_after_expiration_raises(self):
        now = datetime.now(timezone.utc)
        order, line = _order_with_pending_adjustment(expires_at=_iso(now - timedelta(minutes=1)))
        order.expire_customer_approval(now=now)
        with pytest.raises(CustomerApprovalExpiredError):
            order.reject_customer_adjustment(line.id)
