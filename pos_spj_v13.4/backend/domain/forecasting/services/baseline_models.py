"""Baseline forecast models (§19, BI-9).

Pure functions — `Decimal` in, `Decimal` out, no I/O, no persistence,
no statistics library dependency (§131: forecast math may use non-Decimal
internals when a library requires it, but nothing here requires one, so
everything stays `Decimal` end to end for reproducibility). Each function
takes a chronologically-sorted sequence of `TimeSeriesObservation` and a
horizon in days, and returns exactly `horizon_days` point forecasts.

Ported from BI-6's inventory of the legacy engines' pure formulas — the
*fórmula*, never the class:
  - `moving_average`/`weighted_moving_average` ← DemandForecastEngine.moving_avg/weighted_avg
  - `simple_exponential_smoothing`             ← ForecastEngine._ses / DemandForecastEngine.exp_smoothing
  - `holt`/`holt_winters`                      ← ForecastService's Holt-Winters (statsmodels), reimplemented
                                                  here as closed-form Decimal arithmetic — no statsmodels
                                                  dependency, so these stay unit-testable without an optional
                                                  import that BI-6 found already causes a skip in
                                                  `test_forecast_handles_missing_statsmodels.py`.

None of these read a DB — `TimeSeriesDatasetBuilder` (BI-8) supplies the
observations. Confidence intervals are NOT produced here — that requires an
error distribution from backtesting (BI-10); these functions return bare
point-forecast sequences that BI-10/BI-11 wrap into `ForecastResultPoint`s.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from backend.domain.forecasting.exceptions import InsufficientHistoryError
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


def _values(observations: Sequence[TimeSeriesObservation]) -> list[Decimal]:
    if not observations:
        raise InsufficientHistoryError("At least one observation is required")
    return [obs.value for obs in observations]


def _require_horizon(horizon_days: int) -> None:
    if horizon_days <= 0:
        raise ValueError("horizon_days must be > 0")


def naive(observations: Sequence[TimeSeriesObservation], horizon_days: int) -> tuple[Decimal, ...]:
    """§19 — repeats the last observed value for the whole horizon."""
    _require_horizon(horizon_days)
    last = _values(observations)[-1]
    return tuple(last for _ in range(horizon_days))


def seasonal_naive(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    season_length: int = 7,
) -> tuple[Decimal, ...]:
    """§19 — repeats the value observed `season_length` steps back, cycling."""
    _require_horizon(horizon_days)
    if season_length <= 0:
        raise ValueError("season_length must be > 0")
    values = _values(observations)
    if len(values) < season_length:
        raise InsufficientHistoryError(
            f"seasonal_naive requires at least {season_length} observations, got {len(values)}"
        )
    season = values[-season_length:]
    return tuple(season[i % season_length] for i in range(horizon_days))


def moving_average(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    window: int = 7,
) -> tuple[Decimal, ...]:
    """§19 — flat forecast at the average of the last `window` observations."""
    _require_horizon(horizon_days)
    if window <= 0:
        raise ValueError("window must be > 0")
    values = _values(observations)
    if len(values) < window:
        raise InsufficientHistoryError(
            f"moving_average requires at least {window} observations, got {len(values)}"
        )
    avg = sum(values[-window:], Decimal("0")) / Decimal(window)
    return tuple(avg for _ in range(horizon_days))


def weighted_moving_average(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    window: int = 14,
) -> tuple[Decimal, ...]:
    """§19 — flat forecast at a linearly recency-weighted average of the last
    `window` observations (most recent gets the highest weight)."""
    _require_horizon(horizon_days)
    if window <= 0:
        raise ValueError("window must be > 0")
    values = _values(observations)
    if len(values) < window:
        raise InsufficientHistoryError(
            f"weighted_moving_average requires at least {window} observations, got {len(values)}"
        )
    recent = values[-window:]
    weights = [Decimal(i + 1) for i in range(window)]
    weight_sum = sum(weights, Decimal("0"))
    weighted = sum((v * w for v, w in zip(recent, weights)), Decimal("0"))
    avg = weighted / weight_sum
    return tuple(avg for _ in range(horizon_days))


def simple_exponential_smoothing(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    alpha: Decimal = Decimal("0.3"),
) -> tuple[Decimal, ...]:
    """§19 (SES) — flat forecast at the exponentially-smoothed level."""
    _require_horizon(horizon_days)
    if not (Decimal("0") < alpha <= Decimal("1")):
        raise ValueError("alpha must be in (0, 1]")
    values = _values(observations)
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (Decimal("1") - alpha) * level
    return tuple(level for _ in range(horizon_days))


def holt(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    alpha: Decimal = Decimal("0.3"),
    beta: Decimal = Decimal("0.1"),
) -> tuple[Decimal, ...]:
    """§19 — double exponential smoothing (level + trend), extrapolated
    linearly for the horizon."""
    _require_horizon(horizon_days)
    if not (Decimal("0") < alpha <= Decimal("1")):
        raise ValueError("alpha must be in (0, 1]")
    if not (Decimal("0") < beta <= Decimal("1")):
        raise ValueError("beta must be in (0, 1]")
    values = _values(observations)
    if len(values) < 2:
        raise InsufficientHistoryError("holt requires at least 2 observations")

    level = values[0]
    trend = values[1] - values[0]
    for value in values[1:]:
        previous_level = level
        level = alpha * value + (Decimal("1") - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (Decimal("1") - beta) * trend

    return tuple(level + Decimal(h + 1) * trend for h in range(horizon_days))


def holt_winters(
    observations: Sequence[TimeSeriesObservation],
    horizon_days: int,
    alpha: Decimal = Decimal("0.3"),
    beta: Decimal = Decimal("0.1"),
    gamma: Decimal = Decimal("0.1"),
    season_length: int = 7,
) -> tuple[Decimal, ...]:
    """§19 — additive Holt-Winters (level + trend + seasonality). Requires at
    least 2 full seasons of history; closed-form Decimal arithmetic, no
    `statsmodels` dependency."""
    _require_horizon(horizon_days)
    for name, param in (("alpha", alpha), ("beta", beta), ("gamma", gamma)):
        if not (Decimal("0") < param <= Decimal("1")):
            raise ValueError(f"{name} must be in (0, 1]")
    if season_length <= 1:
        raise ValueError("season_length must be > 1")
    values = _values(observations)
    if len(values) < 2 * season_length:
        raise InsufficientHistoryError(
            f"holt_winters requires at least {2 * season_length} observations "
            f"(2 seasons of {season_length}), got {len(values)}"
        )

    season1_avg = sum(values[:season_length], Decimal("0")) / Decimal(season_length)
    season2_avg = sum(values[season_length:2 * season_length], Decimal("0")) / Decimal(season_length)
    level = season1_avg
    trend = (season2_avg - season1_avg) / Decimal(season_length)
    seasonal = [values[i] - season1_avg for i in range(season_length)]

    for t, value in enumerate(values):
        s_idx = t % season_length
        previous_level = level
        level = alpha * (value - seasonal[s_idx]) + (Decimal("1") - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (Decimal("1") - beta) * trend
        seasonal[s_idx] = gamma * (value - level) + (Decimal("1") - gamma) * seasonal[s_idx]

    n = len(values)
    forecasts = []
    for h in range(horizon_days):
        s_idx = (n + h) % season_length
        forecasts.append(level + Decimal(h + 1) * trend + seasonal[s_idx])
    return tuple(forecasts)
