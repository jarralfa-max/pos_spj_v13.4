"""PricingWhatIfService (§42, BI-19) — simulate an arbitrary price change
without saving it as the real price.

Reuses `compute_price_change_impact` (BI-16, extracted in BI-19) — the exact
same formula `PricingIntelligenceService` uses for its auto-picked
recommendation, applied instead to whatever price the caller wants to
explore.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence
from backend.domain.forecasting.services.price_impact import compute_price_change_impact
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
)
from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.exceptions import (
    InsufficientElasticityForSimulationError,
)
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioResult,
)


class PricingWhatIfService:
    def simulate(
        self,
        *,
        scenario: BusinessScenario,
        current_price: Decimal,
        current_cost: Decimal | None,
        elasticity_estimate: PriceElasticityEstimate,
    ) -> ScenarioResult:
        price_change = scenario.get(ScenarioVariableKind.PRICE_CHANGE_PCT)
        if elasticity_estimate.confidence == EstimateConfidence.LOW:
            raise InsufficientElasticityForSimulationError(
                f"Cannot simulate a price change for {elasticity_estimate.product_id} — "
                "elasticity confidence is LOW (§35)"
            )

        simulated_price = current_price * (Decimal("1") + price_change.value / Decimal("100"))
        volume_pct, margin_pct, revenue_pct = compute_price_change_impact(
            current_price=current_price, current_cost=current_cost,
            elasticity=elasticity_estimate.elasticity_coefficient, suggested_price=simulated_price,
        )

        baseline_metrics: dict[str, Decimal] = {
            "price": current_price,
            "expected_volume_change_pct": Decimal("0"),
            "expected_revenue_change_pct": Decimal("0"),
        }
        scenario_metrics: dict[str, Decimal] = {
            "price": simulated_price,
            "expected_volume_change_pct": volume_pct,
            "expected_revenue_change_pct": revenue_pct,
        }
        if margin_pct is not None:
            baseline_metrics["expected_margin_change_pct"] = Decimal("0")
            scenario_metrics["expected_margin_change_pct"] = margin_pct

        return ScenarioResult(
            scenario_id=scenario.id, baseline_metrics=baseline_metrics,
            scenario_metrics=scenario_metrics, evaluated_at=datetime.now(timezone.utc),
        )
