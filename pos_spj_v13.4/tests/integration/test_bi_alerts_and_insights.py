"""FASE 13 — alertas e insights se generan desde datos reales."""
from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.services.bi_dashboard_service import BiDashboardService
from tests.integration import bi_seed as S


def test_alerta_merma_alta():
    conn = S.fresh_db()
    b = S.add_branch(conn)
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(conn, b, [(p, 10, 30.0, 18.0)], when=S.this_month_day())  # ventas 300
    S.add_waste(conn, p, b, 5, 40.0, when=S.this_month_day())  # merma 40 → 13% > 3%
    conn.commit()
    pl = BiDashboardService(BiDashboardQueryService(conn)).build_dashboard(
        DashboardFilters(preset="month"))
    codes = {a["code"] for a in pl.alerts}
    assert "merma_alta" in codes


def test_insights_no_vacios_con_ventas():
    conn = S.fresh_db()
    b = S.add_branch(conn, "San Bartolo")
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(conn, b, [(p, 3, 30.0, 18.0)], when=S.this_month_day())
    conn.commit()
    pl = BiDashboardService(BiDashboardQueryService(conn)).build_dashboard(
        DashboardFilters(preset="month"))
    titulos = " | ".join(i["title"] for i in pl.insights)
    assert "San Bartolo" in titulos
    assert any(i["code"] == "producto_top" for i in pl.insights)
    # ningún insight con texto vacío
    assert all(i["title"] and i["detail"] for i in pl.insights)
