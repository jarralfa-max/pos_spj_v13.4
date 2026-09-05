"""InventoryWhatIfService (§43-44, BI-19) — simulate a demand change's
effect on purchase need.

Takes two already-wired `PurchasePlanningService` instances — one backed by
the real `TimeSeriesReaderPort`, one backed by a `ScaledTimeSeriesReader`
(this phase) applying the scenario's `DEMAND_CHANGE_PCT` — and diffs their
outputs. The scenario mechanism (scaling reads) lives one layer down; this
service only orchestrates baseline vs. scenario and reports the delta.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.forecasting.services.purchase_planning_service import (
    PurchasePlanningService,
)
from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioResult,
)


class InventoryWhatIfService:
    def simulate_purchase_need(
        self,
        *,
        scenario: BusinessScenario,
        baseline_service: PurchasePlanningService,
        scenario_service: PurchasePlanningService,
        position: InventoryPosition,
        horizon_days: int,
        as_of: date,
        overstock_threshold_days: Decimal,
        target_coverage_days: Decimal,
        confidence: Decimal,
        valid_until: date,
        safety_stock_method: SafetyStockMethod = SafetyStockMethod.SERVICE_LEVEL,
        service_level: Decimal = Decimal("0.95"),
        fixed_days: Decimal | None = None,
    ) -> ScenarioResult:
        scenario.get(ScenarioVariableKind.DEMAND_CHANGE_PCT)  # validates presence, unused value
        # (the actual scaling already happened inside scenario_service's reader —
        #  this call only confirms the scenario declares the variable it claims to)

        kwargs = dict(
            position=position, horizon_days=horizon_days, as_of=as_of,
            overstock_threshold_days=overstock_threshold_days,
            target_coverage_days=target_coverage_days, confidence=confidence,
            valid_until=valid_until, safety_stock_method=safety_stock_method,
            service_level=service_level, fixed_days=fixed_days,
        )
        baseline_rec = baseline_service.recommend_purchase(**kwargs)
        scenario_rec = scenario_service.recommend_purchase(**kwargs)

        baseline_metrics = {
            "suggested_quantity": baseline_rec.suggested_quantity if baseline_rec else Decimal("0"),
        }
        scenario_metrics = {
            "suggested_quantity": scenario_rec.suggested_quantity if scenario_rec else Decimal("0"),
        }
        if (baseline_rec is not None and baseline_rec.estimated_cost is not None
                and scenario_rec is not None and scenario_rec.estimated_cost is not None):
            baseline_metrics["estimated_cost"] = baseline_rec.estimated_cost
            scenario_metrics["estimated_cost"] = scenario_rec.estimated_cost

        return ScenarioResult(
            scenario_id=scenario.id, baseline_metrics=baseline_metrics,
            scenario_metrics=scenario_metrics, evaluated_at=datetime.now(timezone.utc),
        )
