"""254 — Forecasting bounded context schema (BI-11).

Creates `forecast_models`/`forecast_runs`/`forecast_result_points`/
`forecast_backtests` — the persistence layer for the canonical
ForecastingPlatform (backend/domain/forecasting/, BI-7..BI-11). These are
NEW tables with zero legacy consumers; no data migration, no coexistence
with the 8 legacy forecast engines' tables (`demand_forecast`,
`replenishment_recommendations`, `product_forecast_config`, etc.) — those
stay untouched until BI-32 (Legacy Removal).

DDL lives solely in `forecasting_schema.py` (same pattern as Procurement's
137/253): re-running this migration is idempotent via CREATE TABLE IF NOT
EXISTS.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema

logger = logging.getLogger("spj.migrations.254")


def run(conn) -> None:
    create_forecasting_schema(conn)
    conn.commit()
    logger.info("254: esquema de forecasting (BI-11) asegurado.")


up = run
