"""ForecastModelSelector (§21, BI-10) — pick the best backtested model.

Pure comparison over already-computed `ForecastBacktest` results; never runs
a backtest itself (that is `ForecastBacktester`, application layer, BI-10).
Only compares metrics that are never `None` (MAE/RMSE/WAPE) — MASE/MAPE/
sMAPE can be `None` for zero/flat series (§22) and are not safe sort keys.
"""

from __future__ import annotations

from typing import Sequence

from backend.domain.forecasting.exceptions import ForecastingDomainError
from backend.domain.forecasting.value_objects.forecast_backtest import ForecastBacktest

_COMPARABLE_METRICS = ("mae", "rmse", "wape")


class NoComparableBacktestsError(ForecastingDomainError):
    pass


def select_best_model(
    backtests: Sequence[ForecastBacktest],
    metric_key: str = "wape",
) -> ForecastBacktest:
    """Lower is better for every supported metric_key."""
    if not backtests:
        raise NoComparableBacktestsError("select_best_model requires at least one backtest")
    if metric_key not in _COMPARABLE_METRICS:
        raise ValueError(
            f"metric_key must be one of {_COMPARABLE_METRICS} (lower-is-better, never None)"
        )
    return min(backtests, key=lambda b: getattr(b.metrics, metric_key))
