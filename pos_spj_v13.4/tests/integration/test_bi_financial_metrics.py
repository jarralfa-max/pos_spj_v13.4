"""FASE 13 — métricas financieras: utilidad, margen, CxC, CxP."""
from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.queries.bi_finance_query_service import BiFinanceQueryService
from tests.integration import bi_seed as S


def _setup():
    conn = S.fresh_db()
    b = S.add_branch(conn)
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(conn, b, [(p, 10, 30.0, 18.0)], when=S.this_month_day())  # ventas 300, cogs 180
    S.add_expense(conn, 50.0, when=S.this_month_day())
    S.add_receivable(conn, 300.0)
    S.add_receivable(conn, 0.0)     # saldada, no cuenta
    S.add_payable(conn, 600.0)
    conn.commit()
    return conn, DashboardFilters(preset="month").resolved()


def test_cxc_cxp_solo_saldos_abiertos():
    conn, f = _setup()
    fin = BiFinanceQueryService(conn)
    assert fin.accounts_receivable_total(f) == 300.0
    assert fin.accounts_payable_total(f) == 600.0


def test_utilidad_y_margen():
    conn, f = _setup()
    m = BiDashboardQueryService(conn).core_metrics(f)
    assert m["ventas_netas"] == 300.0
    assert m["costo_ventas"] == 180.0
    assert m["gastos"] == 50.0
    # utilidad = 300 - 180 - 50 = 70 ; margen = 70/300*100
    assert m["utilidad_neta"] == 70.0
    assert round(m["margen_pct"], 2) == 23.33
