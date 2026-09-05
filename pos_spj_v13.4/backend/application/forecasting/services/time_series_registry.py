"""TimeSeriesRegistry — the one place a canonical series is defined (§8/§17).

Same shape as `backend.application.analytics.services.metric_registry.
MetricRegistry` (BI-3): in-memory, register/get, no persistence yet — a
series is metadata (dimensions/grain/unit/minimum-history), the actual
observations are fetched on demand via a `TimeSeriesReaderPort`
implementation (BI-8 infrastructure), never stored here.
"""

from __future__ import annotations

from backend.domain.forecasting.exceptions import TimeSeriesNotFoundError
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


class TimeSeriesRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, TimeSeriesDefinition] = {}

    def register(self, definition: TimeSeriesDefinition) -> None:
        if definition.key in self._definitions:
            raise ValueError(f"TimeSeriesDefinition already registered: {definition.key}")
        self._definitions[definition.key] = definition

    def get(self, key: str) -> TimeSeriesDefinition:
        try:
            return self._definitions[key]
        except KeyError:
            raise TimeSeriesNotFoundError(f"Serie no registrada: {key}") from None

    def all(self) -> tuple[TimeSeriesDefinition, ...]:
        return tuple(self._definitions.values())
