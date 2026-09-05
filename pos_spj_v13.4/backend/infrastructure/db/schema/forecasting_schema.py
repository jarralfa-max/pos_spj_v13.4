"""Forecasting bounded context — born-clean UUIDv7 schema (BI-11).

Rules (same as every other bounded context's schema module):
- Every id is ``TEXT PRIMARY KEY`` holding a lowercase UUIDv7 (PostgreSQL: UUID).
- Money/quantity/metric columns are ``TEXT`` decimal strings (PostgreSQL:
  NUMERIC) — no REAL.
- A `ForecastRun`/`ForecastResultPoint` is immutable/append-only (§69): there
  is no UPDATE path for these tables, only INSERT.

Only a migration in ``migrations/`` may execute this DDL.
"""

from __future__ import annotations

FORECASTING_TABLES: tuple[str, ...] = (
    "forecast_models",
    "forecast_runs",
    "forecast_result_points",
    "forecast_backtests",
)

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS forecast_models (
        id TEXT PRIMARY KEY,
        model_key TEXT NOT NULL,
        model_family TEXT NOT NULL,
        parameters TEXT NOT NULL DEFAULT '{}',
        training_window_days INTEGER NOT NULL,
        minimum_history_days INTEGER NOT NULL,
        feature_schema TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
            'DRAFT','TESTING','APPROVED','ACTIVE','DEPRECATED','RETIRED')),
        version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        approved_at TEXT,
        UNIQUE (model_key, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecast_runs (
        id TEXT PRIMARY KEY,
        model_version_id TEXT NOT NULL REFERENCES forecast_models(id),
        series_definition_key TEXT NOT NULL,
        scope_policy TEXT NOT NULL,
        scope_value TEXT NOT NULL,
        training_from TEXT NOT NULL,
        training_to TEXT NOT NULL,
        forecast_from TEXT NOT NULL,
        forecast_to TEXT NOT NULL,
        horizon_days INTEGER NOT NULL,
        generated_at TEXT NOT NULL,
        confidence_level TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN (
            'PENDING','RUNNING','COMPLETED','FAILED'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecast_result_points (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES forecast_runs(id),
        point_date TEXT NOT NULL,
        point_forecast TEXT NOT NULL,
        lower_bound TEXT NOT NULL,
        upper_bound TEXT NOT NULL,
        UNIQUE (run_id, point_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forecast_backtests (
        id TEXT PRIMARY KEY,
        model_key TEXT NOT NULL,
        model_version INTEGER NOT NULL,
        series_definition_key TEXT NOT NULL,
        train_from TEXT NOT NULL,
        train_to TEXT NOT NULL,
        test_from TEXT NOT NULL,
        test_to TEXT NOT NULL,
        mae TEXT NOT NULL,
        rmse TEXT NOT NULL,
        mape TEXT,
        smape TEXT,
        wape TEXT NOT NULL,
        bias TEXT NOT NULL,
        mase TEXT,
        evaluated_at TEXT NOT NULL
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_forecast_models_key ON forecast_models(model_key)",
    "CREATE INDEX IF NOT EXISTS idx_forecast_models_status ON forecast_models(model_key, status)",
    "CREATE INDEX IF NOT EXISTS idx_forecast_runs_series"
    " ON forecast_runs(series_definition_key, scope_value)",
    "CREATE INDEX IF NOT EXISTS idx_forecast_result_points_run"
    " ON forecast_result_points(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_forecast_backtests_model"
    " ON forecast_backtests(model_key, model_version)",
)


def create_forecasting_schema(conn) -> None:
    """Create the forecasting tables (idempotent). DDL lives only here."""
    for statement in _DDL:
        conn.execute(statement)
    for index in _INDEXES:
        conn.execute(index)


def drop_forecasting_schema(conn) -> list[str]:
    dropped: list[str] = []
    for table in reversed(FORECASTING_TABLES):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    return dropped
