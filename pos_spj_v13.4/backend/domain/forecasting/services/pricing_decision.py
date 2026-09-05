"""Pricing decision rule (§32-35, BI-16) — pure function from an already-
computed `PriceElasticityEstimate` to a recommendation type/price/expected
impact. Separated from `price_elasticity.py`'s estimation so each half is
independently, exactly testable: estimation from raw history is inherently
approximate; the decision rule given an estimate is deterministic.

Thresholds (`inelastic_threshold=-1`, `elastic_threshold=-1.5`) are the
textbook elasticity-magnitude conventions (|E|=1 is unit elasticity), not
arbitrary UI defaults — same "fixed convention over guesswork" spirit as the
Z-tables already used in `confidence_interval.py`/`safety_stock_policy.py`.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence, PriceRecommendationType
from backend.domain.forecasting.services.price_impact import compute_price_change_impact
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
)

PriceDecision = tuple[PriceRecommendationType, Decimal, Decimal | None, Decimal | None, Decimal | None, str]


def decide_price_recommendation(
    *,
    elasticity_estimate: PriceElasticityEstimate,
    current_price: Decimal,
    current_cost: Decimal | None,
    margin_review_threshold_pct: Decimal,
    price_increase_pct: Decimal = Decimal("5"),
    price_decrease_pct: Decimal = Decimal("5"),
    inelastic_threshold: Decimal = Decimal("-1"),
    elastic_threshold: Decimal = Decimal("-1.5"),
) -> PriceDecision:
    """Returns (type, suggested_price, expected_volume_change_pct,
    expected_margin_change_pct, expected_revenue_change_pct, reason). The
    3 "expected_*_pct" fields are `None` exactly when they can't be computed
    honestly (no cost for margin; REVIEW_REQUIRED/REVIEW_MARGIN never
    project an impact for a price that isn't actually changing)."""
    if elasticity_estimate.confidence == EstimateConfidence.LOW:
        return (
            PriceRecommendationType.REVIEW_REQUIRED, current_price, None, None, None,
            "Historial de precios insuficiente para estimar elasticidad (§35)",
        )

    margin_pct = None
    if current_cost is not None and current_price > 0:
        margin_pct = (current_price - current_cost) / current_price * Decimal("100")

    if margin_pct is not None and margin_pct < margin_review_threshold_pct:
        return (
            PriceRecommendationType.REVIEW_MARGIN, current_price, Decimal("0"), Decimal("0"),
            Decimal("0"),
            f"Margen actual ({margin_pct}%) por debajo del umbral de revisión "
            f"({margin_review_threshold_pct}%)",
        )

    elasticity = elasticity_estimate.elasticity_coefficient
    assert elasticity is not None  # guaranteed by PriceElasticityEstimate's own invariant

    if elasticity > inelastic_threshold:
        rec_type = PriceRecommendationType.INCREASE_PRICE
        suggested_price = current_price * (Decimal("1") + price_increase_pct / Decimal("100"))
        reason = f"Demanda inelástica (E={elasticity}); se espera que un incremento de precio mejore ingresos"
    elif elasticity < elastic_threshold:
        rec_type = PriceRecommendationType.DECREASE_PRICE
        suggested_price = current_price * (Decimal("1") - price_decrease_pct / Decimal("100"))
        reason = f"Demanda elástica (E={elasticity}); se espera que una reducción de precio mejore ingresos"
    else:
        rec_type = PriceRecommendationType.HOLD_PRICE
        suggested_price = current_price
        reason = f"Elasticidad cercana a unitaria (E={elasticity}); mantener precio"

    if rec_type == PriceRecommendationType.HOLD_PRICE:
        return (rec_type, suggested_price, Decimal("0"), Decimal("0"), Decimal("0"), reason)

    volume_change_pct, margin_change_pct, revenue_change_pct = compute_price_change_impact(
        current_price=current_price, current_cost=current_cost, elasticity=elasticity,
        suggested_price=suggested_price, current_margin_pct=margin_pct,
    )

    return (rec_type, suggested_price, volume_change_pct, margin_change_pct, revenue_change_pct, reason)
