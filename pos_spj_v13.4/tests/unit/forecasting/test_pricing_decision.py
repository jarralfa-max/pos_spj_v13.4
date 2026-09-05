from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence, PriceRecommendationType
from backend.domain.forecasting.services.pricing_decision import decide_price_recommendation
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
)


def _estimate(elasticity, confidence=EstimateConfidence.HIGH) -> PriceElasticityEstimate:
    return PriceElasticityEstimate(
        product_id="p1", branch_id="b1", elasticity_coefficient=elasticity,
        sample_size=10, confidence=confidence,
    )


def test_review_required_when_confidence_is_low():
    estimate = _estimate(None, confidence=EstimateConfidence.LOW)
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("60"),
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.REVIEW_REQUIRED
    assert suggested == Decimal("100")
    assert volume is None and margin is None and revenue is None


def test_review_margin_overrides_elasticity_when_margin_too_thin():
    estimate = _estimate(Decimal("-0.5"))  # would otherwise be INCREASE_PRICE
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("80"),
        margin_review_threshold_pct=Decimal("25"),
    )
    # margin = (100-80)/100*100 = 20% < 25% threshold
    assert rec_type == PriceRecommendationType.REVIEW_MARGIN
    assert suggested == Decimal("100")
    assert (volume, margin, revenue) == (Decimal("0"), Decimal("0"), Decimal("0"))


def test_increase_price_when_inelastic():
    estimate = _estimate(Decimal("-0.5"))
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("60"),
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.INCREASE_PRICE
    assert suggested == Decimal("105")
    # price_change_pct=5; volume=-0.5*5=-2.5; revenue=5+(-2.5)=2.5
    assert volume == Decimal("-2.5")
    assert revenue == Decimal("2.5")
    expected_new_margin = (Decimal("105") - Decimal("60")) / Decimal("105") * Decimal("100")
    expected_margin_change = expected_new_margin - Decimal("40")
    assert margin == expected_margin_change


def test_decrease_price_when_elastic():
    estimate = _estimate(Decimal("-2"))
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("60"),
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.DECREASE_PRICE
    assert suggested == Decimal("95")
    # price_change_pct=-5; volume=-2*-5=10; revenue=-5+10=5
    assert volume == Decimal("10")
    assert revenue == Decimal("5")


def test_hold_price_when_near_unit_elastic():
    estimate = _estimate(Decimal("-1.2"))
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("60"),
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.HOLD_PRICE
    assert suggested == Decimal("100")
    assert (volume, margin, revenue) == (Decimal("0"), Decimal("0"), Decimal("0"))


def test_boundary_elasticity_of_exactly_minus_one_holds():
    """-1 is the unit-elasticity boundary — not strictly > -1, so it falls
    into HOLD rather than INCREASE_PRICE."""
    estimate = _estimate(Decimal("-1"))
    rec_type, *_ = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=Decimal("60"),
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.HOLD_PRICE


def test_margin_change_is_none_without_a_cost():
    estimate = _estimate(Decimal("-0.5"))
    rec_type, suggested, volume, margin, revenue, reason = decide_price_recommendation(
        elasticity_estimate=estimate, current_price=Decimal("100"), current_cost=None,
        margin_review_threshold_pct=Decimal("20"),
    )
    assert rec_type == PriceRecommendationType.INCREASE_PRICE
    assert margin is None
    assert volume is not None and revenue is not None
