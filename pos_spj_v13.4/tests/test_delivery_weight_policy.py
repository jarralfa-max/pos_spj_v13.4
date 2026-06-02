import pytest

from core.delivery.domain.policies import DeliveryTotalPolicy, DeliveryWorkflowPolicy, WeightAdjustmentPolicy
from core.delivery.domain.states import AdjustmentStatus


def test_weight_adjustment_within_tolerance_auto_accepts():
    decision = WeightAdjustmentPolicy(tolerance_units=0.2).evaluate(2.0, 2.15, 100)
    assert decision.apply_immediately is True
    assert decision.status == AdjustmentStatus.AUTO_ACCEPTED
    assert decision.new_subtotal == 215.0
    assert decision.diff_pct == 7.5


def test_weight_adjustment_outside_tolerance_requires_customer():
    decision = WeightAdjustmentPolicy(tolerance_units=0.2).evaluate(2.0, 2.25, 100)
    assert decision.apply_immediately is False
    assert decision.status == AdjustmentStatus.PENDING_CUSTOMER
    assert decision.tolerance_exceeded is True


def test_weight_adjustment_zero_requested_does_not_block_on_tolerance():
    decision = WeightAdjustmentPolicy(tolerance_units=0.2).evaluate(0, 0.5, 100)
    assert decision.tolerance_exceeded is False
    assert decision.diff_pct == 0.0
    assert decision.new_subtotal == 50.0


def test_weight_adjustment_rejects_negative_values():
    with pytest.raises(ValueError, match="preparada"):
        WeightAdjustmentPolicy().evaluate(1, -1, 10)


def test_total_policy_rounds_money():
    assert DeliveryTotalPolicy.calculate_total([10.005, 1.005]) == 11.01


def test_workflow_policy_requires_driver_only_for_delivery():
    assert DeliveryWorkflowPolicy.requires_driver("delivery") is True
    assert DeliveryWorkflowPolicy.requires_driver("pickup") is False
