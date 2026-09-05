"""AnalyticalSnapshot (§64) — a reconstructible point-in-time aggregate.

A snapshot is never the source of truth: it can always be rebuilt from the
owning bounded context's transactional data plus the events BI observed
(§64: "No duplicar fuente transaccional. Son proyecciones reconstruibles.").
`source_event_ids` is what makes a snapshot auditable/reconstructible — it
names exactly which events fed it, so a re-run against the same event range
must reproduce the same values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from backend.domain.analytics.enums import ScopePolicy


class SnapshotKind(str, Enum):
    """§64 — the known snapshot families. New kinds are added here, not as
    ad hoc new tables outside this vocabulary (that is exactly how
    `ventas_diarias`/`bi_sales_daily` ended up duplicated — see BI-5)."""
    DAILY_SALES = "DAILY_SALES"
    INVENTORY_DAILY = "INVENTORY_DAILY"
    BRANCH_DAILY = "BRANCH_DAILY"
    PRODUCT_PROFITABILITY = "PRODUCT_PROFITABILITY"
    FORECAST_ACCURACY = "FORECAST_ACCURACY"


@dataclass(frozen=True, slots=True)
class AnalyticalSnapshot:
    kind: SnapshotKind
    scope_policy: ScopePolicy
    scope_value: str
    period: date
    values: dict[str, Decimal]
    computed_at: datetime
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.scope_value:
            raise ValueError("AnalyticalSnapshot.scope_value is required")
        if not self.values:
            raise ValueError("AnalyticalSnapshot.values must not be empty")
        for key, value in self.values.items():
            if not isinstance(value, Decimal):
                raise TypeError(
                    f"AnalyticalSnapshot.values[{key!r}] must be Decimal, got {type(value)}"
                )
        if not self.source_event_ids:
            raise ValueError(
                "AnalyticalSnapshot.source_event_ids is required — a snapshot must be "
                "traceable back to the events that produced it (§64 reconstructibility)"
            )

    def value(self, key: str) -> Decimal:
        return self.values[key]
