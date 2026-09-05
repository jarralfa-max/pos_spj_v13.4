"""ProductionPlanningService (§30/§76, BI-15) — the production-side mirror
of `PurchasePlanningService` (BI-14): same reorder-point trigger, same
"return None when nothing is needed" contract, same "ports for cross-context
data, never a concrete import" discipline via `ProductionCapacityPort`.
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
from backend.domain.forecasting.integration_ports import ProductionCapacityPort
from backend.domain.forecasting.services import safety_stock_policy
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.production_recommendation import (
    ProductionRecommendation,
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


class ProductionPlanningService:
    def __init__(
        self,
        inventory_forecast_service: InventoryForecastService,
        dataset_builder: TimeSeriesDatasetBuilder,
        series_definition: TimeSeriesDefinition,
        capacity_port: ProductionCapacityPort | None = None,
    ) -> None:
        self._inventory_forecast_service = inventory_forecast_service
        self._dataset_builder = dataset_builder
        self._series_definition = series_definition
        self._capacity_port = capacity_port

    def recommend_production(
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
    ) -> ProductionRecommendation | None:
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

        recommended_quantity = safety_stock_policy.recommended_quantity(
            current_stock=position.available_stock(),
            reorder_point_qty=inventory_forecast.reorder_point,
            target_coverage_days=target_coverage_days,
            avg_daily_demand=recent_avg_daily_demand,
        )
        if recommended_quantity == 0:
            return None

        expected_yield_pct = None
        required_raw_material = None
        capacity_utilization_pct = None
        if self._capacity_port is not None:
            expected_yield_pct = self._capacity_port.expected_yield_pct(
                position.product_id, position.branch_id)
            if expected_yield_pct is not None and expected_yield_pct > 0:
                required_raw_material = recommended_quantity / expected_yield_pct
            capacity = self._capacity_port.available_capacity(position.branch_id, as_of)
            if capacity is not None and capacity > 0:
                utilization = recommended_quantity / capacity
                capacity_utilization_pct = (
                    utilization if utilization <= Decimal("1") else Decimal("1")
                ) * Decimal("100")

        days_of_supply = safety_stock_policy.days_coverage(
            position.available_stock(), recent_avg_daily_demand)
        priority = _URGENCY_TO_PRIORITY[safety_stock_policy.urgency_level(days_of_supply)]

        return ProductionRecommendation(
            id=new_uuid(),
            product_id=position.product_id,
            branch_id=position.branch_id,
            recommended_production_quantity=recommended_quantity,
            recommended_processing_date=inventory_forecast.reorder_date,
            expected_demand=recent_avg_daily_demand * target_coverage_days,
            current_stock=position.current_stock,
            expected_yield_pct=expected_yield_pct,
            required_raw_material=required_raw_material,
            capacity_utilization_pct=capacity_utilization_pct,
            priority=priority,
            confidence=confidence,
            created_at=datetime.now(timezone.utc),
            valid_until=valid_until,
        )
