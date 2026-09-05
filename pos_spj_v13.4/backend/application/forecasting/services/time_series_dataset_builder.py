"""TimeSeriesDatasetBuilder (§8, BI-8) — turns a TimeSeriesDefinition +
date range into the observations a forecast model can train on.

This is the seam between the domain's pure `TimeSeriesReaderPort` and a real
consumer (BI-9 models, BI-10 backtesting): it enforces the *definition's own*
`minimum_history_days` before handing data to a model, so "not enough
history" is caught here — once, centrally — instead of every model
re-deriving that check (or worse, silently forecasting off 3 days of data,
which is exactly the kind of thing none of the 8 legacy engines guarded
against consistently, per BI-6).
"""

from __future__ import annotations

from datetime import date

from backend.domain.forecasting.exceptions import InsufficientHistoryError
from backend.domain.forecasting.repository_ports import TimeSeriesReaderPort
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


class TimeSeriesDatasetBuilder:
    def __init__(self, reader: TimeSeriesReaderPort) -> None:
        self._reader = reader

    def build(
        self,
        definition: TimeSeriesDefinition,
        dimension_filter: dict[str, str],
        date_from: date,
        date_to: date,
    ) -> tuple[TimeSeriesObservation, ...]:
        if date_to < date_from:
            raise ValueError("date_to must be >= date_from")
        span_days = (date_to - date_from).days + 1
        if span_days < definition.minimum_history_days:
            raise InsufficientHistoryError(
                f"Serie {definition.key!r} requiere al menos "
                f"{definition.minimum_history_days} días de historial, se pidieron {span_days}"
            )
        unknown = set(dimension_filter) - set(definition.dimension_keys)
        if unknown:
            raise ValueError(
                f"dimension_filter contiene claves no declaradas por {definition.key!r}: "
                f"{sorted(unknown)}"
            )
        return self._reader.read_observations(definition.key, dimension_filter, date_from, date_to)

    def build_test_window(
        self,
        definition: TimeSeriesDefinition,
        dimension_filter: dict[str, str],
        date_from: date,
        date_to: date,
    ) -> tuple[TimeSeriesObservation, ...]:
        """Like `build()` but without the `minimum_history_days` gate — a
        backtest holdout window (BI-10) is legitimately shorter than the
        minimum training history and must not be rejected for that reason."""
        if date_to < date_from:
            raise ValueError("date_to must be >= date_from")
        unknown = set(dimension_filter) - set(definition.dimension_keys)
        if unknown:
            raise ValueError(
                f"dimension_filter contiene claves no declaradas por {definition.key!r}: "
                f"{sorted(unknown)}"
            )
        return self._reader.read_observations(definition.key, dimension_filter, date_from, date_to)
