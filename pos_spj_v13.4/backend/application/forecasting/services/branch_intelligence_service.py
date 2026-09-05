"""BranchIntelligenceService (§31/§74/§77, BI-17).

Two concrete analyses, both built purely from `InventoryForecast` (BI-13) —
no new signal is invented:

  - `analyze_stock_risk()`: aggregates per-product inventory forecasts
    across a branch's product set; if a large-enough share show stockout
    risk, INCREASE_STOCK; if overstock risk dominates, REDUCE_STOCK.
  - `recommend_transfer()`: the same product forecast at two branches —
    a surplus at one covering a deficit at the other, §74.

CHANGE_ASSORTMENT/REVIEW_STAFFING/REVIEW_HOURS/REVIEW_PRICING/
CAPACITY_EXPANSION (the other 5 `BranchRecommendationType` values) need
signals this pipeline doesn't have (staffing, schedules, floor capacity) —
not fabricated here.
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
from backend.domain.forecasting.services import safety_stock_policy
from backend.domain.forecasting.value_objects.branch_recommendation import (
    BranchRecommendation,
    BranchRecommendationType,
    StockTransferRecommendation,
)
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition
from backend.shared.ids import new_uuid


def _priority_from_share(share: Decimal) -> RecommendationPriority:
    if share >= Decimal("0.6"):
        return RecommendationPriority.CRITICAL
    if share >= Decimal("0.4"):
        return RecommendationPriority.HIGH
    return RecommendationPriority.MEDIUM


_URGENCY_TO_PRIORITY = {
    "CRITICAL": RecommendationPriority.CRITICAL,
    "HIGH": RecommendationPriority.HIGH,
    "MEDIUM": RecommendationPriority.MEDIUM,
    "LOW": RecommendationPriority.LOW,
    "NONE": RecommendationPriority.LOW,
}


class BranchIntelligenceService:
    def __init__(
        self,
        inventory_forecast_service: InventoryForecastService,
        dataset_builder: TimeSeriesDatasetBuilder,
        series_definition: TimeSeriesDefinition,
    ) -> None:
        self._inventory_forecast_service = inventory_forecast_service
        self._dataset_builder = dataset_builder
        self._series_definition = series_definition

    def analyze_stock_risk(
        self,
        *,
        branch_id: str,
        positions: tuple[InventoryPosition, ...],
        horizon_days: int,
        as_of: date,
        overstock_threshold_days: Decimal,
        confidence: Decimal,
        valid_until: date,
        stockout_share_threshold: Decimal = Decimal("0.3"),
        overstock_share_threshold: Decimal = Decimal("0.3"),
        safety_stock_method: SafetyStockMethod = SafetyStockMethod.SERVICE_LEVEL,
        service_level: Decimal = Decimal("0.95"),
        fixed_days: Decimal | None = None,
    ) -> BranchRecommendation | None:
        if not positions:
            raise ValueError("positions must not be empty")

        stockout_products: list[str] = []
        overstock_products: list[str] = []
        for position in positions:
            forecast = self._inventory_forecast_service.forecast_inventory(
                position=position, horizon_days=horizon_days, as_of=as_of,
                overstock_threshold_days=overstock_threshold_days,
                safety_stock_method=safety_stock_method, service_level=service_level,
                fixed_days=fixed_days,
            )
            if any(p.stockout_probability > 0 for p in forecast.points):
                stockout_products.append(position.product_id)
            if any(p.overstock_probability > 0 for p in forecast.points):
                overstock_products.append(position.product_id)

        total = Decimal(len(positions))
        stockout_share = Decimal(len(stockout_products)) / total
        overstock_share = Decimal(len(overstock_products)) / total
        now = datetime.now(timezone.utc)

        if stockout_share >= stockout_share_threshold and stockout_share >= overstock_share:
            return BranchRecommendation(
                id=new_uuid(), branch_id=branch_id,
                recommendation_type=BranchRecommendationType.INCREASE_STOCK,
                reason=(
                    f"{len(stockout_products)}/{len(positions)} productos con riesgo "
                    "de quiebre de stock en el horizonte pronosticado"
                ),
                affected_product_ids=tuple(stockout_products),
                priority=_priority_from_share(stockout_share), confidence=confidence,
                created_at=now, valid_until=valid_until,
            )
        if overstock_share >= overstock_share_threshold:
            return BranchRecommendation(
                id=new_uuid(), branch_id=branch_id,
                recommendation_type=BranchRecommendationType.REDUCE_STOCK,
                reason=(
                    f"{len(overstock_products)}/{len(positions)} productos con riesgo "
                    "de sobre-stock en el horizonte pronosticado"
                ),
                affected_product_ids=tuple(overstock_products),
                priority=_priority_from_share(overstock_share), confidence=confidence,
                created_at=now, valid_until=valid_until,
            )
        return None

    def recommend_transfer(
        self,
        *,
        product_id: str,
        source_position: InventoryPosition,
        destination_position: InventoryPosition,
        horizon_days: int,
        as_of: date,
        overstock_threshold_days: Decimal,
        target_coverage_days: Decimal,
        confidence: Decimal,
        valid_until: date,
        safety_stock_method: SafetyStockMethod = SafetyStockMethod.SERVICE_LEVEL,
        service_level: Decimal = Decimal("0.95"),
        fixed_days: Decimal | None = None,
    ) -> StockTransferRecommendation | None:
        source_forecast = self._inventory_forecast_service.forecast_inventory(
            position=source_position, horizon_days=horizon_days, as_of=as_of,
            overstock_threshold_days=overstock_threshold_days,
            safety_stock_method=safety_stock_method, service_level=service_level,
            fixed_days=fixed_days,
        )
        destination_forecast = self._inventory_forecast_service.forecast_inventory(
            position=destination_position, horizon_days=horizon_days, as_of=as_of,
            overstock_threshold_days=overstock_threshold_days,
            safety_stock_method=safety_stock_method, service_level=service_level,
            fixed_days=fixed_days,
        )

        source_has_surplus = any(p.overstock_probability > 0 for p in source_forecast.points)
        if not source_has_surplus or destination_forecast.reorder_date is None:
            return None

        source_surplus = source_position.available_stock() - source_forecast.reorder_point
        if source_surplus <= 0:
            return None

        destination_dimension_filter = {"product": product_id, "branch": destination_position.branch_id}
        destination_avg_demand, _ = compute_recent_average_daily_demand(
            self._dataset_builder, self._series_definition, destination_dimension_filter, as_of)
        destination_need = safety_stock_policy.recommended_quantity(
            current_stock=destination_position.available_stock(),
            reorder_point_qty=destination_forecast.reorder_point,
            target_coverage_days=target_coverage_days,
            avg_daily_demand=destination_avg_demand,
        )
        suggested_quantity = min(source_surplus, destination_need)
        if suggested_quantity <= 0:
            return None

        days_of_supply = safety_stock_policy.days_coverage(
            destination_position.available_stock(), destination_avg_demand)
        priority = _URGENCY_TO_PRIORITY[safety_stock_policy.urgency_level(days_of_supply)]

        return StockTransferRecommendation(
            id=new_uuid(), product_id=product_id,
            source_branch_id=source_position.branch_id,
            destination_branch_id=destination_position.branch_id,
            suggested_quantity=suggested_quantity, priority=priority, confidence=confidence,
            created_at=datetime.now(timezone.utc), valid_until=valid_until,
        )
