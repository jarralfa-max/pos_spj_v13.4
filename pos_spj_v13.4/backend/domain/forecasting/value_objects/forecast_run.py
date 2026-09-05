"""ForecastRun / ForecastResult (§24-25, BI-7).

BI-6 found `ReplenishmentEngine` is the only legacy engine with any run
history at all (`forecast_run_log`), and it has no confidence intervals —
none of the 8 engines do. `ForecastResultPoint` makes an interval mandatory
at construction time so a canonical forecast can never be presented as a
bare point estimate (§25: "No mostrar una predicción como certeza").

Runs are immutable and append-only (§69: never overwrite forecast history) —
nothing here mutates a `ForecastRun` in place; a re-forecast is a new run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class ForecastRun:
    run_id: str
    model_version_id: str
    series_definition_key: str
    scope_policy: ScopePolicy
    scope_value: str
    training_from: date
    training_to: date
    forecast_from: date
    forecast_to: date
    horizon_days: int
    generated_at: datetime
    confidence_level: Decimal
    status: ForecastRunStatus

    def __post_init__(self) -> None:
        validate_uuidv7(self.run_id)
        validate_uuidv7(self.model_version_id)
        if not self.series_definition_key:
            raise ValueError("ForecastRun.series_definition_key is required")
        if not self.scope_value:
            raise ValueError("ForecastRun.scope_value is required")
        if self.training_to < self.training_from:
            raise ValueError("ForecastRun.training_to must be >= training_from")
        if self.forecast_to < self.forecast_from:
            raise ValueError("ForecastRun.forecast_to must be >= forecast_from")
        if self.horizon_days <= 0:
            raise ValueError("ForecastRun.horizon_days must be > 0")
        if not (Decimal("0") < self.confidence_level <= Decimal("1")):
            raise ValueError("ForecastRun.confidence_level must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class ForecastResultPoint:
    timestamp: date
    point_forecast: Decimal
    lower_bound: Decimal
    upper_bound: Decimal

    def __post_init__(self) -> None:
        for name in ("point_forecast", "lower_bound", "upper_bound"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"ForecastResultPoint.{name} must be Decimal, got {type(value)}")
        if not (self.lower_bound <= self.point_forecast <= self.upper_bound):
            raise ValueError(
                "ForecastResultPoint requires lower_bound <= point_forecast <= upper_bound "
                f"(got {self.lower_bound} <= {self.point_forecast} <= {self.upper_bound})"
            )


@dataclass(frozen=True, slots=True)
class ForecastResult:
    run_id: str
    points: tuple[ForecastResultPoint, ...]

    def __post_init__(self) -> None:
        validate_uuidv7(self.run_id)
        if not self.points:
            raise ValueError("ForecastResult.points must not be empty")
        timestamps = [p.timestamp for p in self.points]
        if timestamps != sorted(timestamps):
            raise ValueError("ForecastResult.points must be sorted by timestamp")
