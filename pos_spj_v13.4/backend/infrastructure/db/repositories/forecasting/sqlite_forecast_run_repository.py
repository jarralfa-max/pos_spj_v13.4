"""SQLite implementation of ForecastRunRepositoryPort (BI-11).

Runs and their result points are append-only (§69: never overwrite forecast
history) — `save_run()` is a plain INSERT of both the run row and its
points inside one transaction; there is no update path.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.domain.forecasting.exceptions import ForecastRunNotFoundError
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.shared.ids import new_uuid


def _row_to_run(row) -> ForecastRun:
    return ForecastRun(
        run_id=row["id"],
        model_version_id=row["model_version_id"],
        series_definition_key=row["series_definition_key"],
        scope_policy=ScopePolicy(row["scope_policy"]),
        scope_value=row["scope_value"],
        training_from=date.fromisoformat(row["training_from"]),
        training_to=date.fromisoformat(row["training_to"]),
        forecast_from=date.fromisoformat(row["forecast_from"]),
        forecast_to=date.fromisoformat(row["forecast_to"]),
        horizon_days=row["horizon_days"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        confidence_level=Decimal(row["confidence_level"]),
        status=ForecastRunStatus(row["status"]),
    )


class SqliteForecastRunRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def _cursor(self) -> sqlite3.Cursor:
        cursor = self._conn.cursor()
        cursor.row_factory = sqlite3.Row
        return cursor

    def save_run(self, run: ForecastRun, result: ForecastResult) -> None:
        if result.run_id != run.run_id:
            raise ValueError("ForecastResult.run_id must match ForecastRun.run_id")
        self._conn.execute(
            """
            INSERT INTO forecast_runs (
                id, model_version_id, series_definition_key, scope_policy, scope_value,
                training_from, training_to, forecast_from, forecast_to, horizon_days,
                generated_at, confidence_level, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run.run_id, run.model_version_id, run.series_definition_key,
                run.scope_policy.value, run.scope_value,
                run.training_from.isoformat(), run.training_to.isoformat(),
                run.forecast_from.isoformat(), run.forecast_to.isoformat(),
                run.horizon_days, run.generated_at.isoformat(),
                str(run.confidence_level), run.status.value,
            ),
        )
        for point in result.points:
            self._conn.execute(
                """
                INSERT INTO forecast_result_points (
                    id, run_id, point_date, point_forecast, lower_bound, upper_bound
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    new_uuid(), run.run_id, point.timestamp.isoformat(),
                    str(point.point_forecast), str(point.lower_bound), str(point.upper_bound),
                ),
            )
        self._conn.commit()

    def get_run(self, run_id: str) -> ForecastRun:
        row = self._cursor().execute(
            "SELECT * FROM forecast_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise ForecastRunNotFoundError(f"No existe forecast_runs.id={run_id!r}")
        return _row_to_run(row)

    def get_result(self, run_id: str) -> ForecastResult:
        rows = self._cursor().execute(
            "SELECT * FROM forecast_result_points WHERE run_id = ? ORDER BY point_date",
            (run_id,),
        ).fetchall()
        if not rows:
            raise ForecastRunNotFoundError(f"No hay puntos de resultado para run_id={run_id!r}")
        points = tuple(
            ForecastResultPoint(
                timestamp=date.fromisoformat(r["point_date"]),
                point_forecast=Decimal(r["point_forecast"]),
                lower_bound=Decimal(r["lower_bound"]),
                upper_bound=Decimal(r["upper_bound"]),
            )
            for r in rows
        )
        return ForecastResult(run_id=run_id, points=points)

    def list_runs(self, series_key: str, limit: int = 20) -> tuple[ForecastRun, ...]:
        rows = self._cursor().execute(
            "SELECT * FROM forecast_runs WHERE series_definition_key = ? "
            "ORDER BY generated_at DESC LIMIT ?",
            (series_key, limit),
        ).fetchall()
        return tuple(_row_to_run(r) for r in rows)
