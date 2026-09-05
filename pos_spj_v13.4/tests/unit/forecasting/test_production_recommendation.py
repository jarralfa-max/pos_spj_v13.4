from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import RecommendationPriority
from backend.domain.forecasting.value_objects.production_recommendation import (
    ProductionRecommendation,
)
from backend.shared.ids import new_uuid


def _make(**overrides) -> ProductionRecommendation:
    fields = dict(
        id=new_uuid(), product_id="p1", branch_id="b1",
        recommended_production_quantity=Decimal("100"),
        recommended_processing_date=date(2026, 9, 5),
        expected_demand=Decimal("70"), current_stock=Decimal("20"),
        expected_yield_pct=Decimal("0.8"), required_raw_material=Decimal("125"),
        capacity_utilization_pct=Decimal("50"),
        priority=RecommendationPriority.HIGH, confidence=Decimal("0.9"),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc), valid_until=date(2026, 9, 8),
    )
    fields.update(overrides)
    return ProductionRecommendation(**fields)


def test_valid_recommendation_constructs():
    rec = _make()
    assert rec.required_raw_material == Decimal("125")


def test_yield_and_raw_material_may_be_none():
    rec = _make(expected_yield_pct=None, required_raw_material=None,
                 capacity_utilization_pct=None)
    assert rec.expected_yield_pct is None


def test_rejects_yield_pct_above_one():
    with pytest.raises(ValueError):
        _make(expected_yield_pct=Decimal("1.5"))


def test_rejects_yield_pct_of_zero():
    with pytest.raises(ValueError):
        _make(expected_yield_pct=Decimal("0"))


def test_rejects_negative_quantity():
    with pytest.raises(ValueError):
        _make(recommended_production_quantity=Decimal("-1"))


def test_rejects_confidence_outside_0_1():
    with pytest.raises(ValueError):
        _make(confidence=Decimal("2"))
