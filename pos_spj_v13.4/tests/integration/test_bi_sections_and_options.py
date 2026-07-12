"""FASE 8/3 — datos por sección detallada y catálogos de filtros."""
import pytest

from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.services.bi_dashboard_service import BiDashboardService
from tests.integration import bi_seed as S


@pytest.fixture
def svc():
    conn = S.fresh_db()
    b = S.add_branch(conn, "San Bartolo")
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b,
                      existencia=3, stock_minimo=10)
    S.add_sale(conn, b, [(p, 5, 30.0, 18.0)], forma_pago="efectivo",
               cliente_id="c1", when=S.this_month_day())
    S.add_receivable(conn, 300.0)
    S.add_payable(conn, 600.0)
    S.add_waste(conn, p, b, 2, 40.0, when=S.this_month_day())
    conn.commit()
    return BiDashboardService(BiDashboardQueryService(conn))


def test_filter_options(svc):
    opts = svc.filter_options()
    assert any(b["nombre"] == "San Bartolo" for b in opts["branches"])
    assert "Aves" in opts["categories"]
    assert "efectivo" in opts["payment_methods"]


def test_section_ventas(svc):
    d = svc.section_data("ventas", DashboardFilters(preset="month"))
    assert d["section"] == "ventas"
    assert any(k["title"] == "Ventas netas" for k in d["kpis"])
    assert any(c["title"] == "Métodos de pago" for c in d["charts"])
    assert any(t["title"] == "Top productos" for t in d["tables"])


def test_section_inventario_stock_critico(svc):
    d = svc.section_data("inventario", DashboardFilters(preset="month"))
    stock = next(t for t in d["tables"] if t["title"] == "Stock crítico")
    assert any(r[0] == "Pollo" for r in stock["rows"])


def test_section_finanzas_kpis(svc):
    d = svc.section_data("finanzas", DashboardFilters(preset="month"))
    titles = {k["title"] for k in d["kpis"]}
    assert {"Utilidad neta", "Margen", "CxC", "CxP"} <= titles


def test_section_merma(svc):
    d = svc.section_data("merma", DashboardFilters(preset="month"))
    assert any(k["title"] == "Valor de merma" and k["value"] == 40.0 for k in d["kpis"])


def test_section_desconocida_es_vacia(svc):
    d = svc.section_data("inexistente", DashboardFilters())
    assert d["kpis"] == [] and d["charts"] == [] and d["tables"] == []
