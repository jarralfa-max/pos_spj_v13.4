from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import EstimateConfidence, PriceRecommendationType
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
    PriceRecommendation,
)
from backend.shared.ids import new_uuid


def test_price_elasticity_estimate_low_confidence_must_not_carry_coefficient():
    with pytest.raises(ValueError):
        PriceElasticityEstimate(product_id="p1", branch_id="b1",
                                 elasticity_coefficient=Decimal("-1"), sample_size=2,
                                 confidence=EstimateConfidence.LOW)


def test_price_elasticity_estimate_non_low_requires_coefficient():
    with pytest.raises(ValueError):
        PriceElasticityEstimate(product_id="p1", branch_id="b1",
                                 elasticity_coefficient=None, sample_size=10,
                                 confidence=EstimateConfidence.HIGH)


def test_price_elasticity_estimate_valid_low_case():
    estimate = PriceElasticityEstimate(product_id="p1", branch_id="b1",
                                        elasticity_coefficient=None, sample_size=2,
                                        confidence=EstimateConfidence.LOW)
    assert estimate.elasticity_coefficient is None


def _make_recommendation(**overrides) -> PriceRecommendation:
    fields = dict(
        id=new_uuid(), product_id="p1", branch_id="b1",
        recommendation_type=PriceRecommendationType.INCREASE_PRICE,
        current_price=Decimal("100"), suggested_price=Decimal("105"),
        expected_volume_change_pct=Decimal("-2.5"), expected_margin_change_pct=Decimal("1"),
        expected_revenue_change_pct=Decimal("2.5"), reason="Demanda inelástica",
        confidence=Decimal("0.9"), created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        valid_until=date(2026, 9, 8),
    )
    fields.update(overrides)
    return PriceRecommendation(**fields)


def test_valid_recommendation_constructs():
    rec = _make_recommendation()
    assert rec.recommendation_type == PriceRecommendationType.INCREASE_PRICE


def test_rejects_empty_reason():
    with pytest.raises(ValueError):
        _make_recommendation(reason="")


def test_rejects_negative_prices():
    with pytest.raises(ValueError):
        _make_recommendation(current_price=Decimal("-1"))


def test_rejects_confidence_outside_0_1():
    with pytest.raises(ValueError):
        _make_recommendation(confidence=Decimal("1.1"))


def test_review_required_must_not_change_suggested_price():
    with pytest.raises(ValueError):
        _make_recommendation(
            recommendation_type=PriceRecommendationType.REVIEW_REQUIRED,
            suggested_price=Decimal("110"),
        )
    rec = _make_recommendation(
        recommendation_type=PriceRecommendationType.REVIEW_REQUIRED,
        suggested_price=Decimal("100"), expected_volume_change_pct=None,
        expected_margin_change_pct=None, expected_revenue_change_pct=None,
        reason="Historial insuficiente",
    )
    assert rec.suggested_price == rec.current_price
