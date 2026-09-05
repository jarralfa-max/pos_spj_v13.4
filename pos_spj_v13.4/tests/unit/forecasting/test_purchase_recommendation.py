from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import RecommendationPriority
from backend.domain.forecasting.value_objects.purchase_recommendation import (
    PurchaseRecommendation,
)
from backend.shared.ids import new_uuid


def _make(**overrides) -> PurchaseRecommendation:
    fields = dict(
        id=new_uuid(), product_id="p1", branch_id="b1",
        suggested_quantity=Decimal("100"), coverage_days=Decimal("7"),
        expected_demand=Decimal("70"), current_stock=Decimal("20"),
        incoming_stock=Decimal("0"), safety_stock=Decimal("10"),
        supplier_lead_time_days=3, estimated_cost=Decimal("500"),
        priority=RecommendationPriority.HIGH, confidence=Decimal("0.9"),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc), valid_until=date(2026, 9, 8),
    )
    fields.update(overrides)
    return PurchaseRecommendation(**fields)


def test_valid_recommendation_constructs():
    rec = _make()
    assert rec.priority == RecommendationPriority.HIGH


def test_estimated_cost_may_be_none():
    rec = _make(estimated_cost=None)
    assert rec.estimated_cost is None


def test_rejects_negative_suggested_quantity():
    with pytest.raises(ValueError):
        _make(suggested_quantity=Decimal("-1"))


def test_rejects_negative_estimated_cost():
    with pytest.raises(ValueError):
        _make(estimated_cost=Decimal("-1"))


def test_rejects_confidence_outside_0_1():
    with pytest.raises(ValueError):
        _make(confidence=Decimal("1.5"))


def test_rejects_valid_until_before_created_at():
    with pytest.raises(ValueError):
        _make(created_at=datetime(2026, 9, 10, tzinfo=timezone.utc), valid_until=date(2026, 9, 8))


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _make(id="not-a-uuid")
