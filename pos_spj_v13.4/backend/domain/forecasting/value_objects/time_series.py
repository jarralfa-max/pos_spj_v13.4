"""TimeSeriesDefinition / TimeSeriesObservation (§8/§17-18, BI-8 foundation).

BI-6's engine inventory found that every legacy forecast engine reads sales
history directly via ad hoc SQL and has no explicit policy for days with no
recorded demand (stockouts, closures). `TimeSeriesObservation.is_imputed`
exists specifically so that never happens silently again — §18: "No tratar
días sin stock como demanda cero sin política." A zero must be either a real
observation or an explicit, reasoned imputation; never ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.domain.analytics.enums import TimeGrain

#: §17 — dimensions a series can be keyed by.
VALID_DIMENSION_KEYS = frozenset({
    "product", "category", "branch", "channel",
    "customer_segment", "supplier", "production_line",
})


@dataclass(frozen=True, slots=True)
class TimeSeriesDefinition:
    key: str
    name: str
    dimension_keys: tuple[str, ...]
    time_grain: TimeGrain
    value_unit: str
    minimum_history_days: int
    description: str = ""

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("TimeSeriesDefinition requires key and name")
        unknown = set(self.dimension_keys) - VALID_DIMENSION_KEYS
        if unknown:
            raise ValueError(f"Unknown dimension key(s): {sorted(unknown)}")
        if self.minimum_history_days <= 0:
            raise ValueError("TimeSeriesDefinition.minimum_history_days must be > 0")


@dataclass(frozen=True, slots=True)
class TimeSeriesObservation:
    timestamp: date
    value: Decimal
    is_imputed: bool = False
    imputation_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError(f"TimeSeriesObservation.value must be Decimal, got {type(self.value)}")
        if self.is_imputed and not self.imputation_reason:
            raise ValueError(
                "TimeSeriesObservation.imputation_reason is required when is_imputed=True "
                "(§18: an imputed zero/value must always be explainable)"
            )
        if not self.is_imputed and self.imputation_reason:
            raise ValueError("imputation_reason must only be set when is_imputed=True")
