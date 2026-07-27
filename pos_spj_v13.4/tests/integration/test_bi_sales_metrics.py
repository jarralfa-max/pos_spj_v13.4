"""FASE 13 — métricas de ventas: ventas netas, ticket promedio, órdenes, top."""
from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_sales_query_service import BiSalesQueryService
from tests.integration import bi_seed as S


def _svc_con_ventas():
    conn = S.fresh_db()
    b = S.add_branch(conn)
    p1 = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    p2 = S.add_product(conn, "Costilla", "Carnes", 30.0, branch_id=b)
    d = S.this_month_day()
    S.add_sale(conn, b, [(p1, 2, 30.0, 18.0)], when=d)              # 60
    S.add_sale(conn, b, [(p2, 1, 50.0, 30.0), (p1, 1, 30.0, 18.0)], when=d)  # 80
    conn.commit()
    return BiSalesQueryService(conn), DashboardFilters(preset="month").resolved()


def test_ventas_netas_ordenes_y_ticket():
    svc, f = _svc_con_ventas()
    t = svc.sales_totals(f)
    assert t["ventas_netas"] == 140.0
    assert t["ordenes"] == 2
    assert t["ticket_promedio"] == 70.0


def test_cogs_usa_costo_de_linea():
    svc, f = _svc_con_ventas()
    # costo = 2*18 + (1*30 + 1*18) = 36 + 48 = 84
    assert svc.cost_of_goods(f) == 84.0


def test_top_products_ordenado_por_ingreso():
    svc, f = _svc_con_ventas()
    top = svc.top_products(f)
    assert top[0][0] == "Pollo"   # 60 + 30 = 90 > Costilla 50
    assert top[0][1] == 90.0
