"""FASE 13 — métricas de inventario: valorizado, rotación, stock crítico."""
from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.queries.bi_inventory_query_service import BiInventoryQueryService
from tests.integration import bi_seed as S


def _setup():
    conn = S.fresh_db()
    b = S.add_branch(conn)
    # existencia 5 @ costo 18 → valorizado 90 ; stock_minimo 10 → crítico
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b,
                      existencia=5, stock_minimo=10)
    S.add_sale(conn, b, [(p, 10, 30.0, 18.0)], when=S.this_month_day())  # cogs 180
    conn.commit()
    return conn, b, DashboardFilters(preset="month").resolved()


def test_inventario_valorizado():
    conn, b, f = _setup()
    inv = BiInventoryQueryService(conn)
    assert inv.inventory_valued(f) == 90.0     # 5 * 18


def test_stock_critico():
    conn, b, f = _setup()
    inv = BiInventoryQueryService(conn)
    criticos = inv.critical_stock(f)
    assert any(c["nombre"] == "Pollo" for c in criticos)


def test_rotacion():
    conn, b, f = _setup()
    m = BiDashboardQueryService(conn).core_metrics(f)
    # rotación = cogs / inventario_valorizado = 180 / 90 = 2.0
    assert m["rotacion"] == 2.0
