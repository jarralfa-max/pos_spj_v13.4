"""ForecastBacktest / ForecastAccuracyMetrics (§22, BI-10).

A backtest is the evidence `ForecastModelDefinition` needs before it can
move from `TESTING` to `APPROVED` (§20-23) — it is never optional metadata,
it is the record that justifies the transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class ForecastAccuracyMetrics:
    mae: Decimal
    rmse: Decimal
    mape: Decimal | None
    smape: Decimal | None
    wape: Decimal
    bias: Decimal
    mase: Decimal | None

    def __post_init__(self) -> None:
        for name in ("mae", "rmse", "wape"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"ForecastAccuracyMetrics.{name} must be >= 0, got {value}")
        for name in ("mape", "smape"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"ForecastAccuracyMetrics.{name} must be >= 0 or None, got {value}")


@dataclass(frozen=True, slots=True)
class ForecastBacktest:
    id: str
    model_key: str
    model_version: int
    series_definition_key: str
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    metrics: ForecastAccuracyMetrics
    evaluated_at: datetime

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.model_key:
            raise ValueError("ForecastBacktest.model_key is required")
        if self.model_version < 1:
            raise ValueError("ForecastBacktest.model_version must be >= 1")
        if not self.series_definition_key:
            raise ValueError("ForecastBacktest.series_definition_key is required")
        if self.train_to < self.train_from:
            raise ValueError("ForecastBacktest.train_to must be >= train_from")
        if self.test_to < self.test_from:
            raise ValueError("ForecastBacktest.test_to must be >= test_from")
        if self.test_from <= self.train_to:
            raise ValueError(
                "ForecastBacktest.test_from must be after train_to (out-of-sample holdout)"
            )
