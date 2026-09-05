"""ForecastModelDefinition / ForecastModelVersion (§20-23, BI-7).

BI-6 found that of the 8 legacy engines, only `DemandForecastEngine`
persists any per-series configuration at all (`product_forecast_config`),
and none version that configuration or gate activation behind evidence.
This value object is what replaces all of that: a model is identified by
`model_key` + `version`, and — per §23 (champion/challenger) — a new version
never silently replaces the active one; `status` must move through
`APPROVED` before `ACTIVE`, and `approved_at` is the evidence trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.forecasting.enums import ForecastModelFamily, ForecastModelStatus
from backend.shared.ids import validate_uuidv7

_ACTIVATABLE_STATUSES = frozenset({
    ForecastModelStatus.APPROVED,
    ForecastModelStatus.ACTIVE,
    ForecastModelStatus.DEPRECATED,
    ForecastModelStatus.RETIRED,
})


@dataclass(frozen=True, slots=True)
class ForecastModelDefinition:
    id: str
    model_key: str
    model_family: ForecastModelFamily
    parameters: dict = field(default_factory=dict)
    training_window_days: int = 90
    minimum_history_days: int = 14
    feature_schema: tuple[str, ...] = ()
    status: ForecastModelStatus = ForecastModelStatus.DRAFT
    version: int = 1
    created_at: datetime = None  # type: ignore[assignment]
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.model_key:
            raise ValueError("ForecastModelDefinition.model_key is required")
        if self.version < 1:
            raise ValueError("ForecastModelDefinition.version must be >= 1")
        if self.training_window_days <= 0:
            raise ValueError("ForecastModelDefinition.training_window_days must be > 0")
        if self.minimum_history_days <= 0:
            raise ValueError("ForecastModelDefinition.minimum_history_days must be > 0")
        if self.created_at is None:
            raise ValueError("ForecastModelDefinition.created_at is required")
        if self.status in _ACTIVATABLE_STATUSES and self.approved_at is None:
            raise ValueError(
                f"ForecastModelDefinition.status={self.status} requires approved_at "
                "(§20-23: no model reaches APPROVED/ACTIVE without backtest evidence)"
            )
        if self.status in (ForecastModelStatus.DRAFT, ForecastModelStatus.TESTING) \
                and self.approved_at is not None:
            raise ValueError(
                f"ForecastModelDefinition.status={self.status} must not have approved_at set"
            )

    def is_usable_for_forecasting(self) -> bool:
        return self.status == ForecastModelStatus.ACTIVE
