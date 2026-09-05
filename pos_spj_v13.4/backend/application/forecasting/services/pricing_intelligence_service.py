"""PricingIntelligenceService (§32-35, BI-16) — estimates elasticity from
price/quantity history and applies the pricing decision rule to produce a
`PriceRecommendation`. Never touches a product's actual price (§34: BI
recommends, Pricing decides and creates the new price version).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence
from backend.domain.forecasting.services.price_elasticity import estimate_price_elasticity
from backend.domain.forecasting.services.pricing_decision import decide_price_recommendation
from backend.domain.forecasting.value_objects.price_recommendation import PriceRecommendation
from backend.shared.ids import new_uuid

_CONFIDENCE_BY_ESTIMATE = {
    EstimateConfidence.LOW: Decimal("0"),
    EstimateConfidence.MEDIUM: Decimal("0.5"),
    EstimateConfidence.HIGH: Decimal("0.9"),
}


class PricingIntelligenceService:
    def recommend_price(
        self,
        *,
        product_id: str,
        branch_id: str,
        current_price: Decimal,
        current_cost: Decimal | None,
        price_quantity_history: tuple[tuple[Decimal, Decimal], ...],
        margin_review_threshold_pct: Decimal,
        valid_until: date,
        minimum_points: int = 5,
    ) -> PriceRecommendation:
        elasticity_estimate = estimate_price_elasticity(
            product_id, branch_id, price_quantity_history, minimum_points)
        rec_type, suggested_price, volume_pct, margin_pct, revenue_pct, reason = (
            decide_price_recommendation(
                elasticity_estimate=elasticity_estimate, current_price=current_price,
                current_cost=current_cost, margin_review_threshold_pct=margin_review_threshold_pct,
            )
        )
        return PriceRecommendation(
            id=new_uuid(),
            product_id=product_id,
            branch_id=branch_id,
            recommendation_type=rec_type,
            current_price=current_price,
            suggested_price=suggested_price,
            expected_volume_change_pct=volume_pct,
            expected_margin_change_pct=margin_pct,
            expected_revenue_change_pct=revenue_pct,
            reason=reason,
            confidence=_CONFIDENCE_BY_ESTIMATE[elasticity_estimate.confidence],
            created_at=datetime.now(timezone.utc),
            valid_until=valid_until,
        )
