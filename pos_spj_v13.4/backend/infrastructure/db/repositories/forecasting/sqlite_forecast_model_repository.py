"""SQLite implementation of ForecastModelRepositoryPort (BI-11).

`save()` is an UPSERT keyed by `id` — a `ForecastModelDefinition`'s `id`
identifies one model-version row across its lifecycle (`status` transitions
DRAFT→TESTING→APPROVED→ACTIVE→…, §20); `(model_key, version)` stays the
same for that row, only `status`/`approved_at` change. A genuinely new
training iteration gets a new `id` and a higher `version` (a fresh INSERT),
never overwrites another version's row — that's what the schema's
UNIQUE(model_key, version) constraint guards.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from backend.domain.forecasting.enums import ForecastModelFamily, ForecastModelStatus
from backend.domain.forecasting.exceptions import ForecastModelNotFoundError
from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)


def _row_to_definition(row) -> ForecastModelDefinition:
    return ForecastModelDefinition(
        id=row["id"],
        model_key=row["model_key"],
        model_family=ForecastModelFamily(row["model_family"]),
        parameters=json.loads(row["parameters"]),
        training_window_days=row["training_window_days"],
        minimum_history_days=row["minimum_history_days"],
        feature_schema=tuple(json.loads(row["feature_schema"])),
        status=ForecastModelStatus(row["status"]),
        version=row["version"],
        created_at=datetime.fromisoformat(row["created_at"]),
        approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
    )


class SqliteForecastModelRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def _cursor(self) -> sqlite3.Cursor:
        cursor = self._conn.cursor()
        cursor.row_factory = sqlite3.Row
        return cursor

    def save(self, definition: ForecastModelDefinition) -> None:
        self._conn.execute(
            """
            INSERT INTO forecast_models (
                id, model_key, model_family, parameters, training_window_days,
                minimum_history_days, feature_schema, status, version, created_at, approved_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                approved_at = excluded.approved_at,
                parameters = excluded.parameters,
                feature_schema = excluded.feature_schema
            """,
            (
                definition.id, definition.model_key, definition.model_family.value,
                json.dumps(definition.parameters), definition.training_window_days,
                definition.minimum_history_days, json.dumps(list(definition.feature_schema)),
                definition.status.value, definition.version,
                definition.created_at.isoformat(),
                definition.approved_at.isoformat() if definition.approved_at else None,
            ),
        )
        self._conn.commit()

    def get(self, model_key: str, version: int) -> ForecastModelDefinition:
        row = self._cursor().execute(
            "SELECT * FROM forecast_models WHERE model_key = ? AND version = ?",
            (model_key, version),
        ).fetchone()
        if row is None:
            raise ForecastModelNotFoundError(
                f"No existe forecast_models para model_key={model_key!r} version={version}")
        return _row_to_definition(row)

    def get_active(self, model_key: str) -> ForecastModelDefinition | None:
        row = self._cursor().execute(
            "SELECT * FROM forecast_models WHERE model_key = ? AND status = 'ACTIVE' "
            "ORDER BY version DESC LIMIT 1",
            (model_key,),
        ).fetchone()
        return _row_to_definition(row) if row is not None else None

    def list_versions(self, model_key: str) -> tuple[ForecastModelDefinition, ...]:
        rows = self._cursor().execute(
            "SELECT * FROM forecast_models WHERE model_key = ? ORDER BY version",
            (model_key,),
        ).fetchall()
        return tuple(_row_to_definition(r) for r in rows)
