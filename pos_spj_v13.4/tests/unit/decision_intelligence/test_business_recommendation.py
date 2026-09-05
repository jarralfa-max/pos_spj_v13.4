from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import new_uuid


def _make(**overrides) -> BusinessRecommendation:
    fields = dict(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PURCHASE_MORE,
        target_type="product", target_id="p1", branch_id="b1",
        title="Comprar 20 unidades", summary="Riesgo de quiebre de stock",
        evidence={"suggested_quantity": "20"}, expected_impact="Cobertura de 7 días",
        confidence=Decimal("0.8"), priority=RecommendationPriority.HIGH,
        status=RecommendationStatus.NEW, valid_from=date(2026, 9, 1),
        valid_until=date(2026, 9, 8), created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        model_reference="forecasting.purchase_planning_service",
    )
    fields.update(overrides)
    return BusinessRecommendation(**fields)


def test_valid_recommendation_constructs():
    rec = _make()
    assert rec.recommendation_type == BusinessRecommendationType.PURCHASE_MORE
    assert rec.is_terminal() is False


@pytest.mark.parametrize("status", [
    RecommendationStatus.REJECTED, RecommendationStatus.EXECUTED_EXTERNALLY,
    RecommendationStatus.EXPIRED, RecommendationStatus.DISMISSED,
])
def test_terminal_statuses(status):
    rec = _make(status=status)
    assert rec.is_terminal() is True


@pytest.mark.parametrize("status", [
    RecommendationStatus.NEW, RecommendationStatus.ACKNOWLEDGED,
    RecommendationStatus.UNDER_REVIEW, RecommendationStatus.APPROVED,
])
def test_non_terminal_statuses(status):
    rec = _make(status=status)
    assert rec.is_terminal() is False


def test_rejects_empty_evidence():
    with pytest.raises(ValueError):
        _make(evidence={})


def test_rejects_missing_required_string_fields():
    with pytest.raises(ValueError):
        _make(title="")


def test_rejects_confidence_outside_0_1():
    with pytest.raises(ValueError):
        _make(confidence=Decimal("1.5"))


def test_rejects_valid_until_before_valid_from():
    with pytest.raises(ValueError):
        _make(valid_from=date(2026, 9, 8), valid_until=date(2026, 9, 1))


def test_rejects_valid_from_after_created_at_date():
    with pytest.raises(ValueError):
        _make(valid_from=date(2026, 9, 5),
              created_at=datetime(2026, 9, 1, tzinfo=timezone.utc))


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _make(id="not-a-uuid")


def test_model_reference_and_rule_reference_default_to_none():
    rec = _make(model_reference=None, rule_reference=None)
    assert rec.model_reference is None
    assert rec.rule_reference is None
