import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.application.dto.charts.chart_data import ChartType
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.domain.analytics.enums import ScopePolicy
from backend.shared.ids import new_uuid
from frontend.desktop.modules.business_intelligence.presenters.forecast_explorer_presenter import (
    ForecastExplorerPresenter,
    ForecastUnavailableError,
    _map_forecast_chart,
    _map_run_kpis,
)


def _run(**overrides) -> ForecastRun:
    defaults = dict(
        run_id=new_uuid(), model_version_id=new_uuid(), series_definition_key="k",
        scope_policy=ScopePolicy.BRANCH, scope_value="b1",
        training_from=date(2026, 1, 1), training_to=date(2026, 3, 1),
        forecast_from=date(2026, 3, 2), forecast_to=date(2026, 3, 8),
        horizon_days=7, generated_at=datetime(2026, 3, 1),
        confidence_level=Decimal("0.90"), status=ForecastRunStatus.COMPLETED,
    )
    defaults.update(overrides)
    return ForecastRun(**defaults)


def _result(run_id: str) -> ForecastResult:
    return ForecastResult(run_id=run_id, points=(
        ForecastResultPoint(timestamp=date(2026, 3, 2), point_forecast=Decimal("10"),
                             lower_bound=Decimal("8"), upper_bound=Decimal("12")),
        ForecastResultPoint(timestamp=date(2026, 3, 3), point_forecast=Decimal("11"),
                             lower_bound=Decimal("9"), upper_bound=Decimal("13")),
    ))


def test_map_run_kpis_reports_scope_horizon_confidence_and_status():
    run = _run()
    cards = _map_run_kpis(run)
    by_key = {c.key: c for c in cards}
    assert by_key["scope"].value == "b1"
    assert by_key["horizon"].value == "7 días"
    assert by_key["confidence"].value == "90%"
    assert by_key["status"].value == "COMPLETED"
    assert by_key["status"].variant == "success"


def test_map_run_kpis_marks_non_completed_status_as_warning():
    run = _run(status=ForecastRunStatus.FAILED)
    cards = _map_run_kpis(run)
    assert {c.key: c for c in cards}["status"].variant == "warning"


def test_map_forecast_chart_builds_three_series_from_points():
    run = _run()
    dto = _map_forecast_chart(_result(run.run_id))
    assert dto.chart_type == ChartType.LINE
    assert dto.categories == ("2026-03-02", "2026-03-03")
    by_name = {s.name: s.data for s in dto.series}
    assert by_name["Pronóstico"] == (10.0, 11.0)
    assert by_name["Límite inferior"] == (8.0, 9.0)
    assert by_name["Límite superior"] == (12.0, 13.0)


@pytest.fixture
def conn():
    from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE ventas (id TEXT PRIMARY KEY, estado TEXT, fecha TEXT, sucursal_id TEXT)")
    connection.execute(
        "CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, "
        "producto_id TEXT, cantidad REAL)")
    connection.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, short_name TEXT, "
        "product_type TEXT, base_unit_id TEXT, species_id TEXT, catch_weight_enabled INTEGER, "
        "lot_controlled INTEGER, inventory_managed INTEGER, sellable INTEGER, "
        "purchasable INTEGER, producible INTEGER, internal_only INTEGER, "
        "lifecycle_status TEXT)")
    connection.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    create_forecasting_schema(connection)
    yield connection
    connection.close()


def test_search_products_degrades_gracefully_with_no_rows(conn):
    presenter = ForecastExplorerPresenter(conn)
    assert presenter.search_products("res") == []


def test_search_branches_degrades_gracefully_with_no_rows(conn):
    presenter = ForecastExplorerPresenter(conn)
    assert presenter.search_branches("centro") == []


def test_forecast_requires_a_product_id(conn):
    presenter = ForecastExplorerPresenter(conn)
    with pytest.raises(ForecastUnavailableError):
        presenter.forecast(product_id="", branch_id=None, horizon_days=7)


def test_forecast_requires_a_positive_horizon(conn):
    presenter = ForecastExplorerPresenter(conn)
    with pytest.raises(ForecastUnavailableError):
        presenter.forecast(product_id="p1", branch_id=None, horizon_days=0)


def test_forecast_with_zero_sales_history_raises_a_readable_error_not_a_crash(conn):
    """No sales rows seeded at all: every training day comes back as an
    imputed-zero observation (§18, BI-8), which is real data the backtester
    can run on — but WAPE is genuinely undefined when every actual is zero
    (`accuracy_metrics.wape`'s own domain rule, BI-10). The real
    `MetricInputError` this raises must surface as a readable
    `ForecastUnavailableError`, never an unhandled crash reaching the page."""
    presenter = ForecastExplorerPresenter(conn)
    with pytest.raises(ForecastUnavailableError):
        presenter.forecast(product_id="p1", branch_id="b1", horizon_days=3)


def test_forecast_seeded_history_produces_a_stable_forecast(conn):
    as_of = date.today()
    start = as_of - timedelta(days=120)
    for i in range(120):
        day = start + timedelta(days=i)
        sale_id = new_uuid()
        conn.execute("INSERT INTO ventas (id, estado, fecha, sucursal_id) VALUES (?,?,?,?)",
                     (sale_id, "completada", f"{day.isoformat()} 10:00:00", "b1"))
        conn.execute(
            "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (?,?,?,?)",
            (new_uuid(), sale_id, "p1", 5))
    conn.commit()

    presenter = ForecastExplorerPresenter(conn)
    cards, chart = presenter.forecast(product_id="p1", branch_id="b1", horizon_days=3)
    assert len(chart.categories) == 3
    for value in chart.series[0].data:
        assert value == pytest.approx(5.0)
