"""PurchasePlanningService (§29, BI-14) — turns an `InventoryForecast`
(BI-13) into a `PurchaseRecommendation`, or nothing if no purchase is
actually needed.

`estimated_cost` comes from an injected `FinanceQueryPort` (BI-0's fix for
the legacy forecast service's direct-to-Treasury call violation) — never a
concrete Finance/Treasury import. Passing no port at all is valid;
`estimated_cost` is simply `None` then, never a guess.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.forecasting.services.inventory_forecast_service import (
    InventoryForecastService,
)
from backend.application.forecasting.services.recent_demand_stats import (
    compute_recent_average_daily_demand,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.enums import RecommendationPriority, SafetyStockMethod
from backend.domain.forecasting.integration_ports import FinanceQueryPort
from backend.domain.forecasting.services import safety_stock_policy
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.purchase_recommendation import (
    PurchaseRecommendation,
)
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition
from backend.shared.ids import new_uuid

_URGENCY_TO_PRIORITY = {
    "CRITICAL": RecommendationPriority.CRITICAL,
    "HIGH": RecommendationPriority.HIGH,
    "MEDIUM": RecommendationPriority.MEDIUM,
    "LOW": RecommendationPriority.LOW,
    "NONE": RecommendationPriority.LOW,
}


class PurchasePlanningService:
    def __init__(
        self,
        inventory_forecast_service: InventoryForecastService,
        dataset_builder: TimeSeriesDatasetBuilder,
        series_definition: TimeSeriesDefinition,
        cost_estimator: FinanceQueryPort | None = None,
    ) -> None:
        self._inventory_forecast_service = inventory_forecast_service
        self._dataset_builder = dataset_builder
        self._series_definition = series_definition
        self._cost_estimator = cost_estimator

    def recommend_purchase(
        self,
        *,
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
    ) -> PurchaseRecommendation | None:
        inventory_forecast = self._inventory_forecast_service.forecast_inventory(
            position=position, horizon_days=horizon_days, as_of=as_of,
            overstock_threshold_days=overstock_threshold_days,
            safety_stock_method=safety_stock_method, service_level=service_level,
            fixed_days=fixed_days,
        )
        if inventory_forecast.reorder_date is None:
            return None

        dimension_filter = {"product": position.product_id}
        if position.branch_id:
            dimension_filter["branch"] = position.branch_id
        recent_avg_daily_demand, _ = compute_recent_average_daily_demand(
            self._dataset_builder, self._series_definition, dimension_filter, as_of)

        suggested_quantity = safety_stock_policy.recommended_quantity(
            current_stock=position.available_stock(),
            reorder_point_qty=inventory_forecast.reorder_point,
            target_coverage_days=target_coverage_days,
            avg_daily_demand=recent_avg_daily_demand,
        )
        if suggested_quantity == 0:
            return None

        days_of_supply = safety_stock_policy.days_coverage(
            position.available_stock(), recent_avg_daily_demand)
        priority = _URGENCY_TO_PRIORITY[safety_stock_policy.urgency_level(days_of_supply)]

        estimated_cost = None
        if self._cost_estimator is not None:
            estimated_cost = self._cost_estimator.estimate_purchase_cost(
                position.product_id, suggested_quantity, position.branch_id)

        return PurchaseRecommendation(
            id=new_uuid(),
            product_id=position.product_id,
            branch_id=position.branch_id,
            suggested_quantity=suggested_quantity,
            coverage_days=target_coverage_days,
            expected_demand=recent_avg_daily_demand * target_coverage_days,
            current_stock=position.current_stock,
            incoming_stock=position.incoming_stock,
            safety_stock=inventory_forecast.safety_stock,
            supplier_lead_time_days=position.supplier_lead_time_days,
            estimated_cost=estimated_cost,
            priority=priority,
            confidence=confidence,
            created_at=datetime.now(timezone.utc),
            valid_until=valid_until,
        )
