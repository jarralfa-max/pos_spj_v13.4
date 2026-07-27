"""FASE 13 — el dashboard de resumen devuelve un payload completo y estable."""
import pytest

from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.services.bi_dashboard_service import BiDashboardService
from tests.integration import bi_seed as S


@pytest.fixture
def service():
    conn = S.fresh_db()
    b = S.add_branch(conn)
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(conn, b, [(p, 3, 30.0, 18.0)], when=S.this_month_day())
    conn.commit()
    return BiDashboardService(BiDashboardQueryService(conn))


def test_payload_tiene_todas_las_secciones(service):
    pl = service.build_dashboard(DashboardFilters(preset="month")).to_dict()
    for key in ("filters", "kpis", "charts", "highlights", "alerts",
                "predictions", "insights", "allowed_sections"):
        assert key in pl


def test_kpis_esperadas_presentes(service):
    pl = service.build_dashboard(DashboardFilters(preset="month"))
    keys = {k["key"] for k in pl.kpis}
    assert keys == {
        "ventas_netas", "utilidad_neta", "margen", "ticket_promedio", "ordenes",
        "inventario_valorizado", "cxc", "cxp", "merma", "rotacion",
    }
    # cada KPI documenta su fórmula
    assert all(k["formula"] for k in pl.kpis)


def test_charts_esperados_presentes(service):
    pl = service.build_dashboard(DashboardFilters(preset="month"))
    assert set(pl.charts) == {
        "sales_trend", "branch_sales", "top_products", "categories",
        "payment_methods", "peak_hours", "forecast", "profitability",
    }


def test_cache_devuelve_mismo_payload(service):
    a = service.build_dashboard(DashboardFilters(preset="month"))
    b = service.build_dashboard(DashboardFilters(preset="month"))
    assert a is b  # segundo hit servido de caché
