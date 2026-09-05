"""Repository ports for the forecasting bounded context.

Pure interfaces — no SQL, no db connection type, here. Infrastructure
(BI-11+) implements these against SQLite today and PostgreSQL later without
the domain/application layers changing. BI-6 found every legacy engine reads
its own SQL directly against `detalles_venta`/`ventas` — these ports are
exactly the seam that stops that pattern from recurring in the canonical
platform.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)
from backend.domain.forecasting.value_objects.forecast_run import ForecastResult, ForecastRun
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


class TimeSeriesReaderPort(Protocol):
    def read_observations(
        self,
        series_key: str,
        dimension_filter: dict[str, str],
        date_from: date,
        date_to: date,
    ) -> tuple[TimeSeriesObservation, ...]: ...


class ForecastModelRepositoryPort(Protocol):
    def save(self, definition: ForecastModelDefinition) -> None: ...

    def get(self, model_key: str, version: int) -> ForecastModelDefinition: ...

    def get_active(self, model_key: str) -> ForecastModelDefinition | None: ...

    def list_versions(self, model_key: str) -> tuple[ForecastModelDefinition, ...]: ...


class ForecastRunRepositoryPort(Protocol):
    def save_run(self, run: ForecastRun, result: ForecastResult) -> None: ...

    def get_run(self, run_id: str) -> ForecastRun: ...

    def get_result(self, run_id: str) -> ForecastResult: ...

    def list_runs(self, series_key: str, limit: int = 20) -> tuple[ForecastRun, ...]: ...
