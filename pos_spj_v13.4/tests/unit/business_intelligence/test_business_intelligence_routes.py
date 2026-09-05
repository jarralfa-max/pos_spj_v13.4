import pytest

from frontend.desktop.modules.business_intelligence.business_intelligence_routes import build_page
from frontend.desktop.modules.business_intelligence.pages import BusinessIntelligencePlaceholderPage
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_unknown_route_raises_key_error(qapp):
    with pytest.raises(KeyError):
        build_page("not_a_real_route")


def test_route_without_connection_returns_placeholder(qapp):
    page = build_page("bi_sales")
    assert isinstance(page, BusinessIntelligencePlaceholderPage)


def test_executive_route_without_connection_also_falls_back_to_placeholder(qapp):
    """No `connection` supplied (the default, matching every existing
    caller/test) keeps the placeholder — only a real `connection` triggers
    the real page (BI-24)."""
    page = build_page("bi_executive")
    assert isinstance(page, BusinessIntelligencePlaceholderPage)


def test_production_pricing_and_branches_stay_placeholders_even_with_a_connection(qapp):
    """BI-25 deliberately does not build these three — no dashboard-level
    aggregate query exists behind them, only per-product/per-branch
    recommendation services (BI-14..17) that BI-27's recommendations page
    surfaces instead."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    try:
        for page_id in ("bi_production", "bi_pricing", "bi_branches"):
            page = build_page(page_id, conn)
            assert isinstance(page, BusinessIntelligencePlaceholderPage)
    finally:
        conn.close()
