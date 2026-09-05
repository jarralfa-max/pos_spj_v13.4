"""BI-12 — DemandPlanningService end to end against real SQLite: the
SqliteDailyProductSalesReader (BI-8) reading real ventas/detalles_venta rows,
the SqliteForecastModelRepository/SqliteForecastRunRepository (BI-11)
persisting to the real forecast_* schema (migration 254). This is the first
test in the whole BI-7..BI-12 pipeline that exercises every layer against
one real (in-memory) database connection instead of fakes.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.application.forecasting.services.default_series_catalog import (
    build_default_series_catalog,
    DAILY_SALES_BY_PRODUCT_KEY,
)
from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_model_repository import (
    SqliteForecastModelRepository,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_run_repository import (
    SqliteForecastRunRepository,
)
from backend.infrastructure.db.repositories.forecasting.sqlite_time_series_reader import (
    SqliteDailyProductSalesReader,
)
from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE ventas (id TEXT PRIMARY KEY, estado TEXT, fecha TEXT, sucursal_id TEXT)")
    c.execute("CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, "
              "producto_id TEXT, cantidad REAL)")
    create_forecasting_schema(c)
    yield c
    c.close()


def _seed_constant_sales(conn, *, product_id, branch_id, start, days, quantity):
    for i in range(days):
        day = start + timedelta(days=i)
        sale_id = new_uuid()
        conn.execute("INSERT INTO ventas (id, estado, fecha, sucursal_id) VALUES (?,?,?,?)",
                     (sale_id, "completada", f"{day.isoformat()} 10:00:00", branch_id))
        conn.execute(
            "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (?,?,?,?)",
            (new_uuid(), sale_id, product_id, quantity))
    conn.commit()


def test_demand_planning_end_to_end_against_real_sqlite(conn):
    as_of = date(2026, 12, 1)
    _seed_constant_sales(
        conn, product_id="p1", branch_id="b1",
        start=as_of - timedelta(days=120), days=120, quantity=8)

    reader = SqliteDailyProductSalesReader(conn)
    builder = TimeSeriesDatasetBuilder(reader)
    model_repo = SqliteForecastModelRepository(conn)
    run_repo = SqliteForecastRunRepository(conn)
    series_registry = build_default_series_catalog()
    series_definition = series_registry.get(DAILY_SALES_BY_PRODUCT_KEY)

    service = DemandPlanningService(builder, model_repo, run_repo, series_definition)
    run, result = service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=3, as_of=as_of)

    assert run.status == ForecastRunStatus.COMPLETED
    assert len(result.points) == 3
    for point in result.points:
        assert point.point_forecast == Decimal("8")

    # persisted for real — a second read through the repository sees it
    persisted_run = run_repo.get_run(run.run_id)
    assert persisted_run.scope_value == "b1"
    persisted_result = run_repo.get_result(run.run_id)
    assert len(persisted_result.points) == 3

    # the bootstrapped model is now the ACTIVE one for future calls
    active_model = model_repo.get_active("demand_planning_default")
    assert active_model is not None
    assert active_model.status.value == "ACTIVE"


def test_demand_planning_reflects_a_real_gap_day_as_imputed_zero(conn):
    """A product with a stockout/gap day still produces a usable forecast —
    the imputed zero (§18, BI-8) flows through the whole pipeline without
    crashing anything downstream."""
    as_of = date(2026, 12, 1)
    start = as_of - timedelta(days=120)
    for i in range(120):
        day = start + timedelta(days=i)
        if day == as_of - timedelta(days=30):
            continue  # one gap day, no sales row at all
        sale_id = new_uuid()
        conn.execute("INSERT INTO ventas (id, estado, fecha, sucursal_id) VALUES (?,?,?,?)",
                     (sale_id, "completada", f"{day.isoformat()} 10:00:00", "b1"))
        conn.execute(
            "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (?,?,?,?)",
            (new_uuid(), sale_id, "p1", 8))
    conn.commit()

    reader = SqliteDailyProductSalesReader(conn)
    builder = TimeSeriesDatasetBuilder(reader)
    model_repo = SqliteForecastModelRepository(conn)
    run_repo = SqliteForecastRunRepository(conn)
    series_registry = build_default_series_catalog()
    series_definition = series_registry.get(DAILY_SALES_BY_PRODUCT_KEY)

    service = DemandPlanningService(builder, model_repo, run_repo, series_definition)
    run, result = service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=2, as_of=as_of)

    assert run.status == ForecastRunStatus.COMPLETED
    assert len(result.points) == 2
