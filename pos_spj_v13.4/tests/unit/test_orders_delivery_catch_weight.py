"""ORD-10 — catch-weight adjustment (§26-27): CatchWeightAdjustmentPolicy,
CustomerOrder/CustomerOrderLine weight-evaluation and accept/reject methods,
and OrderTotalsService pricing on final_subtotal."""

from __future__ import annotations

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
from backend.domain.orders_delivery.exceptions import InvalidOrderStateError
from backend.domain.orders_delivery.policies.catch_weight_adjustment_policy import (
    CatchWeightAdjustmentPolicy,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _order_with_catch_weight_line() -> tuple[CustomerOrder, CustomerOrderLine]:
    order = CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.POS, order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER)
    line = CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal("100.00"),
        requested_weight=OrderQuantity(Decimal("2.000"), unit="KG"), catch_weight_enabled=True)
    order.add_line(line)
    return order, line


class TestCatchWeightAdjustmentPolicy:
    def test_within_tolerance(self):
        evaluation = CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("2.000"), prepared_amount=Decimal("2.020"),
            unit_price=Decimal("100"), tolerance_pct=Decimal("5"))
        assert evaluation.within_tolerance
        assert evaluation.proposed_subtotal == Decimal("202.000")

    def test_outside_tolerance(self):
        evaluation = CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("2.000"), prepared_amount=Decimal("2.500"),
            unit_price=Decimal("100"), tolerance_pct=Decimal("5"))
        assert not evaluation.within_tolerance
        assert evaluation.difference_pct == Decimal("25.000")

    def test_zero_requested_with_nonzero_prepared_is_out_of_tolerance(self):
        evaluation = CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("0"), prepared_amount=Decimal("1"),
            unit_price=Decimal("10"), tolerance_pct=Decimal("5"))
        assert not evaluation.within_tolerance

    def test_negative_tolerance_rejected(self):
        from backend.domain.orders_delivery.exceptions import InvalidOrderQuantityError
        with pytest.raises(InvalidOrderQuantityError):
            CatchWeightAdjustmentPolicy.evaluate(
                requested_amount=Decimal("1"), prepared_amount=Decimal("1"),
                unit_price=Decimal("1"), tolerance_pct=Decimal("-1"))


class TestApplyWeightEvaluation:
    def test_within_tolerance_finalizes_immediately(self):
        order, line = _order_with_catch_weight_line()
        line.record_prepared_amount(weight=OrderQuantity(Decimal("2.020"), unit="KG"))
        evaluation = CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("2.000"), prepared_amount=Decimal("2.020"),
            unit_price=Decimal("100"), tolerance_pct=Decimal("5"))
        order.apply_weight_evaluation(line_id=line.id, evaluation=evaluation)
        assert line.status == OrderLineStatus.PREPARED
        assert line.final_weight.value == Decimal("2.020")
        assert order.customer_approval_status == CustomerApprovalStatus.NOT_REQUIRED
        assert order.totals.subtotal == Decimal("202.000")

    def test_outside_tolerance_requires_customer_approval(self):
        order, line = _order_with_catch_weight_line()
        line.record_prepared_amount(weight=OrderQuantity(Decimal("2.500"), unit="KG"))
        evaluation = CatchWeightAdjustmentPolicy.evaluate(
            requested_amount=Decimal("2.000"), prepared_amount=Decimal("2.500"),
            unit_price=Decimal("100"), tolerance_pct=Decimal("5"))
        order.apply_weight_evaluation(line_id=line.id, evaluation=evaluation)
        assert line.status == OrderLineStatus.PENDING_CUSTOMER_APPROVAL
        assert line.final_weight is None
        assert order.customer_approval_status == CustomerApprovalStatus.PENDING
        # Total still reflects requested-equivalent pricing until resolved.
        assert order.totals.subtotal == Decimal("200.000")


class TestAcceptRejectCustomerAdjustment:
    def test_accept_finalizes_and_clears_pending_status(self):
        order, line = _order_with_catch_weight_line()
        line.record_prepared_amount(weight=OrderQuantity(Decimal("2.500"), unit="KG"))
        line.mark_status(OrderLineStatus.PENDING_CUSTOMER_APPROVAL)
        order.customer_approval_status = CustomerApprovalStatus.PENDING
        order.accept_customer_adjustment(line.id)
        assert line.status == OrderLineStatus.PREPARED
        assert line.final_weight.value == Decimal("2.500")
        assert order.customer_approval_status == CustomerApprovalStatus.ACCEPTED
        assert order.totals.subtotal == Decimal("250.000")

    def test_reject_marks_line_rejected(self):
        order, line = _order_with_catch_weight_line()
        line.record_prepared_amount(weight=OrderQuantity(Decimal("2.500"), unit="KG"))
        line.mark_status(OrderLineStatus.PENDING_CUSTOMER_APPROVAL)
        order.reject_customer_adjustment(line.id)
        assert line.status == OrderLineStatus.REJECTED
        assert order.customer_approval_status == CustomerApprovalStatus.REJECTED

    def test_cannot_accept_line_without_pending_adjustment(self):
        order, line = _order_with_catch_weight_line()
        with pytest.raises(InvalidOrderStateError):
            order.accept_customer_adjustment(line.id)
