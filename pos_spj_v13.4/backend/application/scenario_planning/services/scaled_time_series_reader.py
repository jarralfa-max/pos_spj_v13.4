"""ScaledTimeSeriesReader (§43-44, BI-19) — the mechanism behind
`DEMAND_CHANGE_PCT` what-ifs.

Wraps a real `TimeSeriesReaderPort`, multiplying every observed value by a
fixed factor. Never touches real data — it only scales what's read for a
single simulation run, so a "+20% demand" scenario is answered by re-running
the exact same deterministic forecasting/purchase-planning pipeline against
scaled inputs, not by inventing a separate model.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


class ScaledTimeSeriesReader:
    def __init__(self, inner, factor: Decimal) -> None:
        if factor < 0:
            raise ValueError("factor must be >= 0")
        self._inner = inner
        self._factor = factor

    def read_observations(
        self, series_key: str, dimension_filter: dict[str, str], date_from: date, date_to: date
    ) -> tuple[TimeSeriesObservation, ...]:
        observations = self._inner.read_observations(series_key, dimension_filter, date_from, date_to)
        return tuple(
            TimeSeriesObservation(
                timestamp=o.timestamp, value=o.value * self._factor,
                is_imputed=o.is_imputed, imputation_reason=o.imputation_reason,
            )
            for o in observations
        )
