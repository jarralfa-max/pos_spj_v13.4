"""NOTE: does NOT trigger a live forecast/chart render — same documented
QtWebEngine offscreen crash worked around by
`test_executive_dashboard_page.py`. This file only covers page construction,
routing, and the product/branch selection callbacks; the forecast data path
is covered exhaustively by `test_forecast_explorer_presenter.py`.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from backend.infrastructure.db.schema.forecasting_schema import create_forecasting_schema
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.forecast_explorer_page import (
    ForecastExplorerPage,
)
from frontend.desktop.modules.business_intelligence.presenters.forecast_explorer_presenter import (
    ForecastExplorerPresenter,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def conn():
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


def test_page_constructs_without_a_selected_product_or_branch(qapp, conn):
    page = ForecastExplorerPage(ForecastExplorerPresenter(conn))
    assert page._product_id is None
    assert page._branch_id is None
    assert page._loaded is False


def test_ensure_loaded_populates_default_horizon_from_settings(qapp, conn):
    page = ForecastExplorerPage(ForecastExplorerPresenter(conn))
    page.ensure_loaded()
    assert page.horizon.value() == page._presenter.default_horizon_days()
    assert page._loaded is True


def test_selecting_a_product_and_branch_stores_their_ids(qapp, conn):
    page = ForecastExplorerPage(ForecastExplorerPresenter(conn))
    page._select_product(SearchOption(id="p1", label="Res Molida"))
    page._select_branch(SearchOption(id="b1", label="Sucursal Centro"))
    assert page._product_id == "p1"
    assert page._branch_id == "b1"


def test_build_page_with_connection_returns_real_forecast_explorer(qapp, conn):
    page = build_page("bi_forecast", conn)
    assert isinstance(page, ForecastExplorerPage)
