"""build_demand_planning_service (BI-26) — composes a REAL
`DemandPlanningService` from a raw DB connection, using the exact same
wiring `tests/integration/test_demand_planning_service_sqlite.py` already
validates end-to-end (`SqliteDailyProductSalesReader` +
`TimeSeriesDatasetBuilder` + `SqliteForecastModelRepository`/
`SqliteForecastRunRepository` + `build_default_series_catalog()`).

Kept in the application layer so callers (UI presenters, a future API
layer) never import infrastructure repository implementations directly —
per CLAUDE.md's own layering rule, they ask this factory for a ready
service instead.
"""

from __future__ import annotations

from backend.application.forecasting.services.default_series_catalog import (
    DAILY_SALES_BY_PRODUCT_KEY,
    build_default_series_catalog,
)
from backend.application.forecasting.services.demand_planning_service import DemandPlanningService
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_model_repository import (
    SqliteForecastModelRepository,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_run_repository import (
    SqliteForecastRunRepository,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_time_series_reader import (
    SqliteDailyProductSalesReader,
)


def build_demand_planning_service(connection) -> DemandPlanningService:
    reader = SqliteDailyProductSalesReader(connection)
    builder = TimeSeriesDatasetBuilder(reader)
    model_repo = SqliteForecastModelRepository(connection)
    run_repo = SqliteForecastRunRepository(connection)
    series_definition = build_default_series_catalog().get(DAILY_SALES_BY_PRODUCT_KEY)
    return DemandPlanningService(builder, model_repo, run_repo, series_definition)
