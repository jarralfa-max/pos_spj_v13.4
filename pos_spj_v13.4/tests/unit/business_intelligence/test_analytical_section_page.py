"""NOTE: does NOT call `page.ensure_loaded()`/`refresh()` on a real page —
same documented QtWebEngine offscreen crash worked around by
`test_executive_dashboard_page.py`. This file only covers page construction
and routing; the KPI/chart/table data path is covered exhaustively by
`test_analytical_section_presenter.py`.
"""

import sqlite3

import pytest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages.analytical_section_page import (
    AnalyticalSectionPage,
)
from frontend.desktop.modules.business_intelligence.presenters.analytical_section_presenter import (
    AnalyticalSectionPresenter,
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


def test_page_constructs_without_loading_charts_or_tables(qapp, conn):
    page = AnalyticalSectionPage(
        AnalyticalSectionPresenter(conn, "ventas"), title="Ventas", subtitle="x")
    assert page.charts == []
    assert page._tables == []
    assert page._loaded is False


@pytest.mark.parametrize("page_id", ["bi_sales", "bi_inventory", "bi_purchasing", "bi_finance"])
def test_build_page_with_connection_returns_real_analytical_section(qapp, conn, page_id):
    page = build_page(page_id, conn)
    assert isinstance(page, AnalyticalSectionPage)
