"""Data path (simulate) is covered exhaustively by
`test_pricing_scenario_presenter.py`; this file only covers page
construction, routing, and the product/branch selection callbacks.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.pricing_scenario_page import (
    PricingScenarioPage,
)
from frontend.desktop.modules.business_intelligence.presenters.pricing_scenario_presenter import (
    PricingScenarioPresenter,
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
        "CREATE TABLE detalles_venta (id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, "
        "cantidad REAL, precio_unitario REAL)")
    connection.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, short_name TEXT, "
        "product_type TEXT, base_unit_id TEXT, species_id TEXT, catch_weight_enabled INTEGER, "
        "lot_controlled INTEGER, inventory_managed INTEGER, sellable INTEGER, "
        "purchasable INTEGER, producible INTEGER, internal_only INTEGER, "
        "lifecycle_status TEXT)")
    connection.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    connection.execute(
        "CREATE TABLE product_cost (product_id TEXT, branch_id TEXT, average_cost REAL)")
    yield connection
    connection.close()


def test_page_constructs_without_a_selected_product_or_branch(qapp, conn):
    page = PricingScenarioPage(PricingScenarioPresenter(conn))
    assert page._product_id is None
    assert page._branch_id is None
    assert page.price_change_pct.value() == 0


def test_selecting_a_product_and_branch_stores_their_ids(qapp, conn):
    page = PricingScenarioPage(PricingScenarioPresenter(conn))
    page._select_product(SearchOption(id="p1", label="Res Molida"))
    page._select_branch(SearchOption(id="b1", label="Sucursal Centro"))
    assert page._product_id == "p1"
    assert page._branch_id == "b1"


def test_build_page_with_connection_returns_real_pricing_scenario_page(qapp, conn):
    page = build_page("bi_scenarios", conn)
    assert isinstance(page, PricingScenarioPage)
