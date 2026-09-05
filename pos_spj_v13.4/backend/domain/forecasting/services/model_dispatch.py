"""Dispatch table: ForecastModelFamily -> baseline model function (BI-9).

Only the families BI-9 actually implements are mapped. The future-stage
families reserved in `ForecastModelFamily` (ARIMA/SARIMA/ETS/
GRADIENT_BOOSTED_TREES, §19 "etapa posterior") raise `NotImplementedError`
until a later phase implements them — never silently fall back to a
different model than the one requested.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Sequence

from backend.domain.forecasting.enums import ForecastModelFamily
from backend.domain.forecasting.services import baseline_models as bm
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation

BaselineModelFn = Callable[..., tuple[Decimal, ...]]

BASELINE_MODEL_DISPATCH: dict[ForecastModelFamily, BaselineModelFn] = {
    ForecastModelFamily.NAIVE: bm.naive,
    ForecastModelFamily.SEASONAL_NAIVE: bm.seasonal_naive,
    ForecastModelFamily.MOVING_AVERAGE: bm.moving_average,
    ForecastModelFamily.WEIGHTED_MOVING_AVERAGE: bm.weighted_moving_average,
    ForecastModelFamily.SES: bm.simple_exponential_smoothing,
    ForecastModelFamily.HOLT: bm.holt,
    ForecastModelFamily.HOLT_WINTERS: bm.holt_winters,
}


def run_baseline_model(
    family: ForecastModelFamily,
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    parameters: dict | None = None,
) -> tuple[Decimal, ...]:
    fn = BASELINE_MODEL_DISPATCH.get(family)
    if fn is None:
        raise NotImplementedError(
            f"ForecastModelFamily.{family.value} has no baseline implementation yet"
        )
    return fn(observations, horizon_days, **(parameters or {}))
