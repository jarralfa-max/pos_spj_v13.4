from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.scenario_planning.services.pricing_what_if_service import (
    PricingWhatIfService,
)
from backend.domain.forecasting.enums import EstimateConfidence
from backend.domain.forecasting.services.price_impact import compute_price_change_impact
from backend.domain.forecasting.value_objects.price_recommendation import (
    PriceElasticityEstimate,
)
from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.exceptions import (
    InsufficientElasticityForSimulationError,
    MissingScenarioVariableError,
)
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioVariable,
)
from backend.shared.ids import new_uuid


def _scenario(pct: Decimal) -> BusinessScenario:
    return BusinessScenario(
        id=new_uuid(), name="Precio",
        variables=(ScenarioVariable(kind=ScenarioVariableKind.PRICE_CHANGE_PCT, value=pct),),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def _estimate(elasticity, confidence=EstimateConfidence.HIGH) -> PriceElasticityEstimate:
    return PriceElasticityEstimate(
        product_id="p1", branch_id="b1", elasticity_coefficient=elasticity,
        sample_size=10, confidence=confidence,
    )


def test_simulate_price_increase_matches_hand_computed_impact():
    service = PricingWhatIfService()
    scenario = _scenario(Decimal("10"))
    result = service.simulate(
        scenario=scenario, current_price=Decimal("100"), current_cost=Decimal("60"),
        elasticity_estimate=_estimate(Decimal("-0.5")),
    )
    assert result.scenario_metrics["price"] == Decimal("110")
    assert result.delta("price") == Decimal("10")
    # price_change_pct=10; volume=-0.5*10=-5; revenue=10+(-5)=5
    assert result.scenario_metrics["expected_volume_change_pct"] == Decimal("-5")
    assert result.scenario_metrics["expected_revenue_change_pct"] == Decimal("5")

    expected_volume, expected_margin, expected_revenue = compute_price_change_impact(
        current_price=Decimal("100"), current_cost=Decimal("60"), elasticity=Decimal("-0.5"),
        suggested_price=Decimal("110"),
    )
    assert result.scenario_metrics["expected_margin_change_pct"] == expected_margin
    assert result.baseline_metrics["expected_margin_change_pct"] == Decimal("0")


def test_simulate_without_cost_omits_margin_key():
    service = PricingWhatIfService()
    scenario = _scenario(Decimal("10"))
    result = service.simulate(
        scenario=scenario, current_price=Decimal("100"), current_cost=None,
        elasticity_estimate=_estimate(Decimal("-0.5")),
    )
    assert "expected_margin_change_pct" not in result.scenario_metrics
    assert "expected_margin_change_pct" not in result.baseline_metrics


def test_raises_when_elasticity_confidence_is_low():
    service = PricingWhatIfService()
    scenario = _scenario(Decimal("10"))
    low_estimate = PriceElasticityEstimate(
        product_id="p1", branch_id="b1", elasticity_coefficient=None,
        sample_size=2, confidence=EstimateConfidence.LOW,
    )
    with pytest.raises(InsufficientElasticityForSimulationError):
        service.simulate(
            scenario=scenario, current_price=Decimal("100"), current_cost=Decimal("60"),
            elasticity_estimate=low_estimate,
        )


def test_raises_when_scenario_missing_price_change_variable():
    service = PricingWhatIfService()
    scenario = BusinessScenario(
        id=new_uuid(), name="Demanda",
        variables=(ScenarioVariable(kind=ScenarioVariableKind.DEMAND_CHANGE_PCT,
                                     value=Decimal("20")),),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(MissingScenarioVariableError):
        service.simulate(
            scenario=scenario, current_price=Decimal("100"), current_cost=Decimal("60"),
            elasticity_estimate=_estimate(Decimal("-0.5")),
        )
