"""NOTE: does not need the QtWebEngine workaround other BI pages use (this
page has no `HtmlChartView`) but still avoids calling `refresh()` on a real
DB-backed presenter here — the data path (generate + lifecycle transitions)
is covered exhaustively by `test_price_recommendation_presenter.py`; this
file only covers page construction, routing, and the selection/lifecycle
button callbacks.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.decision_intelligence.value_objects.business_recommendation import (
    BusinessRecommendation,
)
from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import new_uuid
from datetime import date, datetime
from decimal import Decimal

from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.price_recommendation_page import (
    PriceRecommendationPage,
)
from frontend.desktop.modules.business_intelligence.presenters.price_recommendation_presenter import (
    PriceRecommendationPresenter,
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


def _recommendation() -> BusinessRecommendation:
    return BusinessRecommendation(
        id=new_uuid(), recommendation_type=BusinessRecommendationType.PRICE_DECREASE,
        target_type="product", target_id="p1", branch_id="b1",
        title="t", summary="s", evidence={"current_price": "16"}, expected_impact="i",
        confidence=Decimal("0.8"), priority=RecommendationPriority.MEDIUM,
        status=RecommendationStatus.NEW, valid_from=date(2026, 1, 1),
        valid_until=date(2026, 2, 1), created_at=datetime(2026, 1, 1),
    )


def test_page_constructs_without_a_selected_product_or_branch(qapp, conn):
    page = PriceRecommendationPage(PriceRecommendationPresenter(conn))
    assert page._product_id is None
    assert page._branch_id is None
    assert page._recommendation is None


def test_ensure_loaded_populates_settings_driven_defaults(qapp, conn):
    page = PriceRecommendationPage(PriceRecommendationPresenter(conn))
    page.ensure_loaded()
    assert page.margin_threshold.value() == page._presenter.default_margin_review_threshold_pct()
    assert page.valid_for_days.value() == page._presenter.default_valid_for_days()


def test_selecting_a_product_and_branch_stores_their_ids(qapp, conn):
    page = PriceRecommendationPage(PriceRecommendationPresenter(conn))
    page._select_product(SearchOption(id="p1", label="Res Molida"))
    page._select_branch(SearchOption(id="b1", label="Sucursal Centro"))
    assert page._product_id == "p1"
    assert page._branch_id == "b1"


def test_apply_transition_without_a_recommendation_shows_a_message_not_a_crash(qapp, conn, monkeypatch):
    page = PriceRecommendationPage(PriceRecommendationPresenter(conn))
    from PyQt5.QtWidgets import QMessageBox
    calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: calls.append(a))
    page._apply_transition("acknowledge")
    assert len(calls) == 1


def test_apply_transition_updates_the_in_memory_recommendation(qapp, conn):
    page = PriceRecommendationPage(PriceRecommendationPresenter(conn))
    page._recommendation = _recommendation()
    page._apply_transition("acknowledge")
    assert page._recommendation.status.value == "ACKNOWLEDGED"


def test_build_page_with_connection_returns_real_price_recommendation_page(qapp, conn):
    page = build_page("bi_recommendations", conn)
    assert isinstance(page, PriceRecommendationPage)
