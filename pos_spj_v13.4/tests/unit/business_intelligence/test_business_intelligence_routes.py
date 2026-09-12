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


def test_only_production_stays_a_placeholder_with_a_connection(qapp):
    """Eran tres; queda una.

    Esta prueba fijaba que Produccion, Precios y Sucursales siguieran vacias
    porque "no existe consulta agregada a nivel de tablero" detras. Para dos de
    las tres dejo de ser cierto: `BiSalesQueryService.by_branch()` y
    `profitability_by_category/product()` ya calculaban esos agregados y nadie
    los mostraba (PASS 6).

    Produccion SI sigue vacia, y por un motivo concreto: la fachada
    `BiDashboardQueryService` expone sales/inventory/finance/forecast/cash y
    ninguna fuente de produccion. `ProductionQueryService` existe pero recibe
    `QueryFilters` en vez de `DashboardFilters`, asi que conectarlo es adaptar
    un contrato, no anadir una clave.
    """
    import sqlite3
    conn = sqlite3.connect(":memory:")
    try:
        assert isinstance(build_page("bi_production", conn),
                          BusinessIntelligencePlaceholderPage)
        for page_id in ("bi_pricing", "bi_branches"):
            assert not isinstance(build_page(page_id, conn),
                                  BusinessIntelligencePlaceholderPage), (
                f"{page_id} volvio a ser placeholder")
    finally:
        conn.close()
