from decimal import Decimal

import pytest

from backend.domain.meat_processing.enums import YieldStatus
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.domain.meat_processing.policies import (
    ConsumptionPolicy,
    OrderClosingPolicy,
    ProcessingOrderCloseChecklist,
    YieldReconciliationPolicy,
)


# -- YieldReconciliationPolicy -------------------------------------------------

def test_yield_classification_bands():
    kwargs = dict(warning_pct=Decimal("2"), tolerance_pct=Decimal("5"),
                  critical_pct=Decimal("10"))
    assert YieldReconciliationPolicy.classify(Decimal("1"), **kwargs) == YieldStatus.WITHIN_TOLERANCE
    assert YieldReconciliationPolicy.classify(Decimal("-1"), **kwargs) == YieldStatus.WITHIN_TOLERANCE
    assert YieldReconciliationPolicy.classify(Decimal("3"), **kwargs) == YieldStatus.WARNING
    assert YieldReconciliationPolicy.classify(Decimal("7"), **kwargs) == YieldStatus.OUT_OF_TOLERANCE
    assert YieldReconciliationPolicy.classify(Decimal("15"), **kwargs) == YieldStatus.CRITICAL
    assert YieldReconciliationPolicy.classify(Decimal("-15"), **kwargs) == YieldStatus.CRITICAL


def test_yield_classification_none_variance_is_pending_review():
    result = YieldReconciliationPolicy.classify(
        None, warning_pct=Decimal("2"), tolerance_pct=Decimal("5"), critical_pct=Decimal("10"))
    assert result == YieldStatus.PENDING_REVIEW


def test_yield_classification_rejects_out_of_order_thresholds():
    with pytest.raises(MeatProcessingInvariantError):
        YieldReconciliationPolicy.classify(
            Decimal("1"), warning_pct=Decimal("10"), tolerance_pct=Decimal("5"),
            critical_pct=Decimal("2"))


def test_yield_classification_rejects_negative_thresholds():
    with pytest.raises(MeatProcessingInvariantError):
        YieldReconciliationPolicy.classify(
            Decimal("1"), warning_pct=Decimal("-1"), tolerance_pct=Decimal("5"),
            critical_pct=Decimal("10"))


# -- ConsumptionPolicy ----------------------------------------------------------

def test_consumption_within_tolerance_passes():
    ConsumptionPolicy.validate_overage(
        Decimal("100"), Decimal("104"), tolerance_pct=Decimal("5"))


def test_consumption_over_tolerance_raises():
    with pytest.raises(MeatProcessingInvariantError):
        ConsumptionPolicy.validate_overage(
            Decimal("100"), Decimal("110"), tolerance_pct=Decimal("5"))


def test_consumption_under_planned_never_raises():
    ConsumptionPolicy.validate_overage(
        Decimal("100"), Decimal("50"), tolerance_pct=Decimal("0"))


def test_consumption_with_zero_planned_and_positive_actual_raises():
    with pytest.raises(MeatProcessingInvariantError):
        ConsumptionPolicy.validate_overage(
            Decimal("0"), Decimal("1"), tolerance_pct=Decimal("100"))


def test_consumption_with_zero_planned_and_zero_actual_passes():
    ConsumptionPolicy.validate_overage(Decimal("0"), Decimal("0"), tolerance_pct=Decimal("0"))


# -- OrderClosingPolicy -----------------------------------------------------------

def _checklist(**overrides) -> ProcessingOrderCloseChecklist:
    base = dict(
        consumptions_posted=True, outputs_registered=True, no_pending_weighings=True,
        quality_resolved=True, yield_calculated=True, variances_reviewed=True,
        critical_losses_have_case=True, inventory_confirmed=True, costs_notified=True,
    )
    base.update(overrides)
    return ProcessingOrderCloseChecklist(**base)


def test_complete_checklist_allows_close():
    OrderClosingPolicy.ensure_can_close(_checklist())


def test_incomplete_checklist_blocks_close_and_lists_pending_items():
    checklist = _checklist(quality_resolved=False, costs_notified=False)
    assert checklist.pending_items == ("quality_resolved", "costs_notified")
    with pytest.raises(MeatProcessingInvariantError):
        OrderClosingPolicy.ensure_can_close(checklist)
