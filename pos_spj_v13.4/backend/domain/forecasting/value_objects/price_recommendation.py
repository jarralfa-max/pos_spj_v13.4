"""PriceElasticityEstimate / PriceRecommendation (§32-35, BI-16).

BI recommends a price change; Pricing decides and creates the new price
version (§34: BI never executes `UPDATE productos SET precio = ...`). No
execution method exists here, deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence, PriceRecommendationType
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class PriceElasticityEstimate:
    product_id: str
    branch_id: str
    elasticity_coefficient: Decimal | None
    sample_size: int
    confidence: EstimateConfidence

    def __post_init__(self) -> None:
        if not self.product_id or not self.branch_id:
            raise ValueError("PriceElasticityEstimate requires product_id and branch_id")
        if self.sample_size < 0:
            raise ValueError("PriceElasticityEstimate.sample_size must be >= 0")
        if self.confidence == EstimateConfidence.LOW and self.elasticity_coefficient is not None:
            raise ValueError(
                "PriceElasticityEstimate with LOW confidence must not carry a coefficient "
                "(§35: no inventar elasticidad)"
            )
        if self.confidence != EstimateConfidence.LOW and self.elasticity_coefficient is None:
            raise ValueError("PriceElasticityEstimate above LOW confidence requires a coefficient")


@dataclass(frozen=True, slots=True)
class PriceRecommendation:
    id: str
    product_id: str
    branch_id: str
    recommendation_type: PriceRecommendationType
    current_price: Decimal
    suggested_price: Decimal
    expected_volume_change_pct: Decimal | None
    expected_margin_change_pct: Decimal | None
    expected_revenue_change_pct: Decimal | None
    reason: str
    confidence: Decimal
    created_at: datetime
    valid_until: date

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.product_id or not self.branch_id:
            raise ValueError("PriceRecommendation requires product_id and branch_id")
        if self.current_price < 0 or self.suggested_price < 0:
            raise ValueError("PriceRecommendation prices must be >= 0")
        if not self.reason:
            raise ValueError("PriceRecommendation.reason is required (§40: explicabilidad)")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("PriceRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.created_at.date():
            raise ValueError("PriceRecommendation.valid_until must be >= created_at date")
        if (self.recommendation_type == PriceRecommendationType.REVIEW_REQUIRED
                and self.suggested_price != self.current_price):
            raise ValueError("REVIEW_REQUIRED must not suggest a different price (§35)")
