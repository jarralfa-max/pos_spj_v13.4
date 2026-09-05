"""MetricRegistry — the one place a metric formula is defined (§11: "No
duplicar fórmulas en widgets").

This is intentionally in-memory/programmatic in BI-3, not DB-backed: the
point of the semantic layer is that a chart/KPI card/export asks the
registry for a `MetricDefinition` instead of hardcoding a formula string.
Persisting metric definitions (versioning across deploys, admin-editable
metrics) is a BI-4+ concern once real QueryServices consume this registry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.analytics.exceptions import MetricNotFoundError
from backend.domain.analytics.services.metric_lineage_service import build_lineage
from backend.domain.analytics.value_objects.metric_definition import MetricDefinition
from backend.domain.analytics.value_objects.metric_lineage import MetricLineage


class MetricRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> None:
        existing = self._definitions.get(definition.key)
        if existing is not None and existing.version >= definition.version:
            raise ValueError(
                f"MetricDefinition {definition.key} version {definition.version} does not "
                f"advance past the already-registered version {existing.version}"
            )
        self._definitions[definition.key] = definition

    def get(self, key: str) -> MetricDefinition:
        try:
            return self._definitions[key]
        except KeyError:
            raise MetricNotFoundError(f"Métrica no registrada: {key}") from None

    def all(self) -> tuple[MetricDefinition, ...]:
        return tuple(self._definitions.values())

    def by_domain_owner(self, domain_owner: str) -> tuple[MetricDefinition, ...]:
        return tuple(m for m in self._definitions.values() if m.domain_owner == domain_owner)

    def lineage_for(
        self,
        key: str,
        *,
        period_description: str,
        filters_applied: tuple[str, ...] = (),
        computed_at: datetime | None = None,
    ) -> MetricLineage:
        definition = self.get(key)
        return build_lineage(
            definition,
            period_description=period_description,
            filters_applied=filters_applied,
            computed_at=computed_at or datetime.now(timezone.utc),
        )
