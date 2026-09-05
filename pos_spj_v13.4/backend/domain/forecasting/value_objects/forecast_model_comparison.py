"""ForecastModelComparison — champion vs challenger (§23, BI-11).

A new model version never silently replaces the active one. This value
object is the evidence record an approval workflow reads before flipping a
challenger's status to `ACTIVE` — it names both models, the metric
compared, both values, and which one wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.forecasting.value_objects.forecast_backtest import ForecastBacktest

_COMPARABLE_METRICS = ("mae", "rmse", "wape")


@dataclass(frozen=True, slots=True)
class ForecastModelComparison:
    champion_model_key: str
    champion_version: int
    challenger_model_key: str
    challenger_version: int
    metric_key: str
    champion_value: Decimal
    challenger_value: Decimal
    challenger_wins: bool

    def __post_init__(self) -> None:
        if self.metric_key not in _COMPARABLE_METRICS:
            raise ValueError(f"metric_key must be one of {_COMPARABLE_METRICS}")


def compare(
    champion: ForecastBacktest,
    challenger: ForecastBacktest,
    metric_key: str = "wape",
) -> ForecastModelComparison:
    """Lower is better for every supported metric_key."""
    if metric_key not in _COMPARABLE_METRICS:
        raise ValueError(f"metric_key must be one of {_COMPARABLE_METRICS}")
    champion_value = getattr(champion.metrics, metric_key)
    challenger_value = getattr(challenger.metrics, metric_key)
    return ForecastModelComparison(
        champion_model_key=champion.model_key,
        champion_version=champion.model_version,
        challenger_model_key=challenger.model_key,
        challenger_version=challenger.model_version,
        metric_key=metric_key,
        champion_value=champion_value,
        challenger_value=challenger_value,
        challenger_wins=challenger_value < champion_value,
    )
