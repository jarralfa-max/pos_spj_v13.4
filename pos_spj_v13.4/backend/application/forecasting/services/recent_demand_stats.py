"""Shared helper: recent-window average daily demand.

Used by `InventoryForecastService` (BI-13, to size safety stock) and
`PurchasePlanningService`/`ProductionPlanningService` (BI-14/BI-15, to size
suggested quantities) — one place computes this instead of each service
repeating the same "read the last N days, average them" logic.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.exceptions import ForecastingDomainError
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


def compute_recent_average_daily_demand(
    dataset_builder: TimeSeriesDatasetBuilder,
    series_definition: TimeSeriesDefinition,
    dimension_filter: dict[str, str],
    as_of: date,
    window_days: int = 14,
) -> tuple[Decimal, tuple[Decimal, ...]]:
    """Returns (average, raw_values) over `[as_of - window_days, as_of - 1]`."""
    if window_days <= 0:
        raise ValueError("window_days must be > 0")
    recent_from = as_of - timedelta(days=window_days)
    recent_to = as_of - timedelta(days=1)
    observations = dataset_builder.build_test_window(
        series_definition, dimension_filter, recent_from, recent_to)
    if not observations:
        raise ForecastingDomainError("No recent observations available to compute demand stats")
    values = tuple(o.value for o in observations)
    average = sum(values, Decimal("0")) / Decimal(len(values))
    return average, values
