"""MetricLineage — answers "¿Cómo se calcula?" for any KPI on screen (§12).

A user with permission must be able to open any KPI card and see exactly
where the number came from: formula, period, filters, freshness and metric
version. This value object is what that dialog renders; it is built by
`MetricLineageService` from a `MetricDefinition` plus the evaluation context
(the concrete period/filters/timestamp a particular number was computed
with) — never invented in the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.domain.analytics.enums import FreshnessPolicy


@dataclass(frozen=True, slots=True)
class MetricLineage:
    metric_key: str
    metric_version: int
    formula: str
    domain_owner: str
    period_description: str
    filters_applied: tuple[str, ...]
    freshness_policy: FreshnessPolicy
    computed_at: datetime

    def __post_init__(self) -> None:
        if not self.metric_key:
            raise ValueError("MetricLineage.metric_key is required")
        if not self.formula:
            raise ValueError("MetricLineage.formula is required")
        if not self.period_description:
            raise ValueError("MetricLineage.period_description is required")
