from datetime import date
from decimal import Decimal

from backend.application.forecasting.services.pricing_intelligence_service import (
    PricingIntelligenceService,
)
from backend.domain.forecasting.enums import PriceRecommendationType

_PERFECT_UNIT_ELASTIC_HISTORY = tuple(
    (Decimal(p), Decimal("100") / Decimal(p))
    for p in (1, 2, 4, 5, 8, 10, 20, 25, 40, 50)
)


def test_end_to_end_hold_price_for_unit_elastic_history():
    service = PricingIntelligenceService()
    rec = service.recommend_price(
        product_id="p1", branch_id="b1", current_price=Decimal("100"),
        current_cost=Decimal("50"), price_quantity_history=_PERFECT_UNIT_ELASTIC_HISTORY,
        margin_review_threshold_pct=Decimal("20"), valid_until=date(2026, 9, 10),
    )
    assert rec.recommendation_type == PriceRecommendationType.HOLD_PRICE
    assert rec.suggested_price == Decimal("100")
    assert rec.confidence == Decimal("0.9")  # HIGH confidence bucket


def test_end_to_end_review_required_with_insufficient_history():
    service = PricingIntelligenceService()
    thin_history = ((Decimal("100"), Decimal("50")),)
    rec = service.recommend_price(
        product_id="p1", branch_id="b1", current_price=Decimal("100"),
        current_cost=Decimal("50"), price_quantity_history=thin_history,
        margin_review_threshold_pct=Decimal("20"), valid_until=date(2026, 9, 10),
    )
    assert rec.recommendation_type == PriceRecommendationType.REVIEW_REQUIRED
    assert rec.confidence == Decimal("0")
