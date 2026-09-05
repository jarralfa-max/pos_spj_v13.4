"""build_inventory_forecast (§28, BI-13) — pure projection of demand
forecast + current stock position into `InventoryForecast`.

Uses the demand `ForecastResult`'s own confidence band (point/lower/upper
per day, from BI-11) as the source of "expected" vs "high-demand"/
"low-demand" scenarios — no separate probability model invented. The tail
probability associated with the upper/lower bound is exactly
`1 - confidence_level` (the same number `ForecastRun.confidence_level`
already carries), so `stockout_probability`/`overstock_probability` are
honest about being confidence-band-derived, not a fitted distribution.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.forecasting.services import safety_stock_policy
from backend.domain.forecasting.value_objects.forecast_run import ForecastResult
from backend.domain.forecasting.value_objects.inventory_forecast import (
    InventoryForecast,
    InventoryForecastPoint,
    InventoryPosition,
)


def build_inventory_forecast(
    *,
    demand_result: ForecastResult,
    position: InventoryPosition,
    safety_stock_qty: Decimal,
    confidence_level_complement: Decimal,
    overstock_threshold_days: Decimal,
    recent_avg_daily_demand: Decimal,
) -> InventoryForecast:
    if not (Decimal("0") <= confidence_level_complement <= Decimal("1")):
        raise ValueError("confidence_level_complement must be in [0, 1]")
    if overstock_threshold_days <= 0:
        raise ValueError("overstock_threshold_days must be > 0")
    if recent_avg_daily_demand < 0:
        raise ValueError("recent_avg_daily_demand must be >= 0")

    reorder_point_qty = safety_stock_policy.reorder_point(
        recent_avg_daily_demand, position.supplier_lead_time_days, safety_stock_qty)
    overstock_qty_threshold = overstock_threshold_days * recent_avg_daily_demand

    available_start = position.available_stock()
    cumulative_point = Decimal("0")
    cumulative_lower = Decimal("0")
    cumulative_upper = Decimal("0")

    points: list[InventoryForecastPoint] = []
    reorder_date: date | None = None

    for result_point in demand_result.points:
        cumulative_point += result_point.point_forecast
        cumulative_lower += result_point.lower_bound
        cumulative_upper += result_point.upper_bound

        incoming = (
            position.incoming_stock
            if position.incoming_arrival_date is not None
            and position.incoming_arrival_date <= result_point.timestamp
            else Decimal("0")
        )

        projected_point = available_start + incoming - cumulative_point
        projected_low_demand = available_start + incoming - cumulative_lower
        projected_high_demand = available_start + incoming - cumulative_upper

        if projected_point < 0:
            stockout_probability = Decimal("1")
        elif projected_high_demand < 0:
            stockout_probability = confidence_level_complement
        else:
            stockout_probability = Decimal("0")

        if projected_point > overstock_qty_threshold:
            overstock_probability = Decimal("1")
        elif projected_low_demand > overstock_qty_threshold:
            overstock_probability = confidence_level_complement
        else:
            overstock_probability = Decimal("0")

        clamped_stock = projected_point if projected_point > 0 else Decimal("0")
        days_of_supply = safety_stock_policy.days_coverage(clamped_stock, recent_avg_daily_demand)

        if reorder_date is None and projected_point <= reorder_point_qty:
            reorder_date = result_point.timestamp

        points.append(InventoryForecastPoint(
            date=result_point.timestamp,
            projected_stock=projected_point,
            days_of_supply=days_of_supply,
            stockout_probability=stockout_probability,
            overstock_probability=overstock_probability,
        ))

    return InventoryForecast(
        product_id=position.product_id,
        branch_id=position.branch_id,
        safety_stock=safety_stock_qty,
        reorder_point=reorder_point_qty,
        reorder_date=reorder_date,
        points=tuple(points),
    )
