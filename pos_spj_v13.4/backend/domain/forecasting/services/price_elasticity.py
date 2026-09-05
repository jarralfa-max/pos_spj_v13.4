"""Price elasticity estimation (§32/§35, BI-16).

Ordinary least squares on ln(price) vs ln(quantity) — the standard
log-log/constant-elasticity model, giving a slope that IS the elasticity
coefficient directly. `Decimal.ln()` (context-based) keeps this end-to-end
`Decimal`, no float/numpy dependency.

§35 is explicit: "Si no hay historial suficiente: confidence = LOW,
recommendation = REVIEW_REQUIRED. No inventar elasticidad." — this function
never returns a fabricated slope when there isn't enough genuine price
variation to estimate one; it returns `(None, EstimateConfidence.LOW)`.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
)


def estimate_price_elasticity(
    product_id: str,
    branch_id: str,
    price_quantity_history: tuple[tuple[Decimal, Decimal], ...],
    minimum_points: int = 5,
) -> PriceElasticityEstimate:
    valid = [(p, q) for p, q in price_quantity_history if p > 0 and q > 0]
    distinct_prices = {p for p, _ in valid}

    if len(valid) < minimum_points or len(distinct_prices) < 2:
        return PriceElasticityEstimate(
            product_id=product_id, branch_id=branch_id,
            elasticity_coefficient=None, sample_size=len(valid),
            confidence=EstimateConfidence.LOW,
        )

    xs = [p.ln() for p, _ in valid]
    ys = [q.ln() for _, q in valid]
    n = Decimal(len(valid))
    mean_x = sum(xs, Decimal("0")) / n
    mean_y = sum(ys, Decimal("0")) / n
    numerator = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)), Decimal("0"))
    denominator = sum(((x - mean_x) * (x - mean_x) for x in xs), Decimal("0"))

    if denominator == 0:
        return PriceElasticityEstimate(
            product_id=product_id, branch_id=branch_id,
            elasticity_coefficient=None, sample_size=len(valid),
            confidence=EstimateConfidence.LOW,
        )

    slope = numerator / denominator
    confidence = (
        EstimateConfidence.HIGH if len(valid) >= minimum_points * 2
        else EstimateConfidence.MEDIUM
    )
    return PriceElasticityEstimate(
        product_id=product_id, branch_id=branch_id,
        elasticity_coefficient=slope, sample_size=len(valid), confidence=confidence,
    )
