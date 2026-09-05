"""Pure domain service: builds a MetricLineage from a MetricDefinition."""

from __future__ import annotations

from datetime import datetime

from backend.domain.analytics.value_objects.metric_definition import MetricDefinition
from backend.domain.analytics.value_objects.metric_lineage import MetricLineage


def build_lineage(
    definition: MetricDefinition,
    *,
    period_description: str,
    filters_applied: tuple[str, ...],
    computed_at: datetime,
) -> MetricLineage:
    return MetricLineage(
        metric_key=definition.key,
        metric_version=definition.version,
        formula=definition.formula,
        domain_owner=definition.domain_owner,
        period_description=period_description,
        filters_applied=filters_applied,
        freshness_policy=definition.freshness_policy,
        computed_at=computed_at,
    )
