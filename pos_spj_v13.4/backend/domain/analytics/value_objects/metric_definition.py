"""MetricDefinition — the single source of truth for one KPI's shape (§11).

Every metric shown anywhere in BI (dashboard card, chart, drilldown table,
export) must resolve to exactly one `MetricDefinition`. The formula lives
here as documentation/lineage metadata (§12) — the *executable* aggregation
lives in the query layer (BI-4); this value object never touches SQL or a DB
connection, it is pure metadata so it can be shared by desktop UI, exports
and the future web API without dragging in infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.analytics.enums import (
    AggregationType,
    CurrencyBehavior,
    FreshnessPolicy,
    ScopePolicy,
    TimeGrain,
)


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    name: str
    description: str
    domain_owner: str
    formula: str
    unit: str
    aggregation: AggregationType
    dimensions: tuple[str, ...]
    time_grain: TimeGrain
    currency_behavior: CurrencyBehavior
    permission: str
    scope_policy: ScopePolicy
    freshness_policy: FreshnessPolicy
    version: int = 1

    def __post_init__(self) -> None:
        if not self.key or not self.key.isupper() or " " in self.key:
            raise ValueError(f"MetricDefinition.key must be UPPER_SNAKE_CASE: {self.key!r}")
        if not self.name:
            raise ValueError("MetricDefinition.name is required")
        if not self.formula:
            raise ValueError("MetricDefinition.formula is required (§12 lineage)")
        if not self.domain_owner:
            raise ValueError("MetricDefinition.domain_owner is required")
        if not self.permission:
            raise ValueError("MetricDefinition.permission is required (§104-114)")
        if self.version < 1:
            raise ValueError("MetricDefinition.version must be >= 1")

    def versioned_key(self) -> str:
        """Stable identity for a specific formula revision — used by
        MetricLineage so a dashboard can say exactly which version of a
        metric produced a given number (§69: never overwrite history)."""
        return f"{self.key}@v{self.version}"


@dataclass(frozen=True, slots=True)
class DimensionDefinition:
    """A slice a metric can be broken down by (product/branch/category/…)."""
    key: str
    name: str
    description: str = ""
    applies_to_domains: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("DimensionDefinition requires key and name")


@dataclass(frozen=True, slots=True)
class MeasureDefinition:
    """A raw underlying numeric fact a metric aggregates over (e.g. the
    line-item `total_amount` a `NET_SALES` metric sums) — distinct from a
    metric, which is a named, permissioned, versioned formula over one or
    more measures."""
    key: str
    name: str
    unit: str
    currency_behavior: CurrencyBehavior
    description: str = ""

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("MeasureDefinition requires key and name")
