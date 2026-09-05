"""InventoryForecastService (§28, BI-13) — ties `DemandPlanningService`
(BI-12) to `build_inventory_forecast` (domain, this phase): gets the demand
forecast, computes a recent-history-based safety stock via the requested
`SafetyStockMethod` (§72), and projects stock forward.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.recent_demand_stats import (
    compute_recent_average_daily_demand,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.services import safety_stock_policy
from backend.domain.forecasting.services.inventory_forecast_builder import (
    build_inventory_forecast,
)
from backend.domain.forecasting.value_objects.inventory_forecast import (
    InventoryForecast,
    InventoryPosition,
)
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


class InventoryForecastService:
    def __init__(
        self,
        demand_planning_service: DemandPlanningService,
        dataset_builder: TimeSeriesDatasetBuilder,
        series_definition: TimeSeriesDefinition,
    ) -> None:
        self._demand_planning_service = demand_planning_service
        self._dataset_builder = dataset_builder
        self._series_definition = series_definition

    def forecast_inventory(
        self,
        *,
        position: InventoryPosition,
        horizon_days: int,
        as_of: date,
        overstock_threshold_days: Decimal,
        safety_stock_method: SafetyStockMethod = SafetyStockMethod.SERVICE_LEVEL,
        service_level: Decimal = Decimal("0.95"),
        fixed_days: Decimal | None = None,
        lead_time_std_dev_days: Decimal = Decimal("0"),
        custom_safety_stock: Decimal | None = None,
        recent_window_days: int = 14,
    ) -> InventoryForecast:
        run, result = self._demand_planning_service.forecast_product_demand(
            product_id=position.product_id, branch_id=position.branch_id,
            horizon_days=horizon_days, as_of=as_of)

        dimension_filter = {"product": position.product_id}
        if position.branch_id:
            dimension_filter["branch"] = position.branch_id
        recent_avg_daily_demand, recent_values = compute_recent_average_daily_demand(
            self._dataset_builder, self._series_definition, dimension_filter,
            as_of, recent_window_days)

        safety_stock_qty = safety_stock_policy.safety_stock(
            safety_stock_method,
            avg_daily_demand=recent_avg_daily_demand,
            lead_time_days=position.supplier_lead_time_days,
            daily_demand_history=recent_values,
            service_level=service_level,
            fixed_days=fixed_days,
            lead_time_std_dev_days=lead_time_std_dev_days,
            custom_value=custom_safety_stock,
        )

        return build_inventory_forecast(
            demand_result=result,
            position=position,
            safety_stock_qty=safety_stock_qty,
            confidence_level_complement=Decimal("1") - run.confidence_level,
            overstock_threshold_days=overstock_threshold_days,
            recent_avg_daily_demand=recent_avg_daily_demand,
        )
