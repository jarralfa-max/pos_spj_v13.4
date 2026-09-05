"""NOTE: does NOT call `page.ensure_loaded()`/`refresh()` on a real page —
that builds `HtmlChartView` (QtWebEngine) and calls `.set_chart()`, which is
a documented, pre-existing crash/hang under this environment's headless
offscreen platform (see `tests/integration/inventory/test_inventory_ui_
presenter.py`'s own `TestPagesSmoke` — it excludes `InventoryAnalyticsPage`
for the exact same reason). The KPI/chart *data* path (what `refresh()`
would feed the widgets) is already fully covered by
`test_executive_dashboard_presenter.py`; this file only covers page
construction and routing, never a live chart render.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.executive_dashboard_page import (
    ExecutiveDashboardPage,
)
from frontend.desktop.modules.business_intelligence.presenters.executive_dashboard_presenter import (
    ExecutiveDashboardPresenter,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_page_constructs_without_loading_charts(qapp, conn):
    page = ExecutiveDashboardPage(ExecutiveDashboardPresenter(conn))
    assert page.charts == []
    assert page._loaded is False


def test_build_page_with_connection_returns_real_executive_dashboard(qapp, conn):
    page = build_page("bi_executive", conn)
    assert isinstance(page, ExecutiveDashboardPage)
