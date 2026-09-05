from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import ForecastModelFamily
from backend.domain.forecasting.services.model_dispatch import run_baseline_model
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


def _series(values: list[int]) -> tuple[TimeSeriesObservation, ...]:
    start = date(2026, 8, 1)
    return tuple(
        TimeSeriesObservation(timestamp=start + timedelta(days=i), value=Decimal(str(v)))
        for i, v in enumerate(values)
    )


@pytest.mark.parametrize("family", [
    ForecastModelFamily.NAIVE,
    ForecastModelFamily.SEASONAL_NAIVE,
    ForecastModelFamily.MOVING_AVERAGE,
    ForecastModelFamily.WEIGHTED_MOVING_AVERAGE,
    ForecastModelFamily.SES,
    ForecastModelFamily.HOLT,
    ForecastModelFamily.HOLT_WINTERS,
])
def test_every_baseline_family_dispatches_without_error(family):
    obs = _series([10, 12, 11, 13, 14, 12, 13] * 3)  # 21 points, enough for all models
    result = run_baseline_model(family, obs, horizon_days=3)
    assert len(result) == 3
    assert all(isinstance(v, Decimal) for v in result)


def test_dispatch_passes_parameters_through():
    obs = _series([10, 20])
    result = run_baseline_model(
        ForecastModelFamily.SES, obs, horizon_days=1, parameters={"alpha": Decimal("1")})
    # alpha=1 means SES tracks the last value exactly
    assert result == (Decimal("20"),)


@pytest.mark.parametrize("family", [
    ForecastModelFamily.ARIMA, ForecastModelFamily.SARIMA,
    ForecastModelFamily.ETS, ForecastModelFamily.GRADIENT_BOOSTED_TREES,
])
def test_future_stage_families_raise_not_implemented(family):
    obs = _series([1, 2, 3])
    with pytest.raises(NotImplementedError):
        run_baseline_model(family, obs, horizon_days=1)
