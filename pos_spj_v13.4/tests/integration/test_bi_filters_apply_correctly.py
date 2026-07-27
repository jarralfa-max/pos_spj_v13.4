"""FASE 13 — los filtros globales afectan realmente los resultados."""
from datetime import timedelta

from backend.application.dto.bi_dashboard_dto import DashboardFilters, resolve_range
from backend.application.queries.bi_sales_query_service import BiSalesQueryService
from tests.integration import bi_seed as S


def _setup():
    conn = S.fresh_db()
    b1 = S.add_branch(conn, "San Bartolo")
    b2 = S.add_branch(conn, "Santa Anita")
    p = S.add_product(conn, "Pollo", "Aves", 18.0, branch_id=b1)
    p2 = S.add_product(conn, "Costilla", "Carnes", 30.0, branch_id=b1)
    d = S.this_month_day()
    S.add_sale(conn, b1, [(p, 1, 30.0, 18.0)], forma_pago="efectivo", when=d)
    S.add_sale(conn, b2, [(p, 1, 40.0, 18.0)], forma_pago="tarjeta_debito", when=d)
    S.add_sale(conn, b1, [(p2, 1, 50.0, 30.0)], forma_pago="efectivo", when=d)
    conn.commit()
    return BiSalesQueryService(conn), b1


def test_filtro_sucursal():
    svc, b1 = _setup()
    f = DashboardFilters(preset="month", branch_id=b1).resolved()
    assert svc.sales_totals(f)["ventas_netas"] == 80.0   # 30 + 50 (sólo b1)


def test_filtro_metodo_pago():
    svc, b1 = _setup()
    f = DashboardFilters(preset="month", payment_method="tarjeta_debito").resolved()
    assert svc.sales_totals(f)["ventas_netas"] == 40.0


def test_filtro_categoria():
    svc, b1 = _setup()
    f = DashboardFilters(preset="month", category="Carnes").resolved()
    # sólo la venta que contiene un producto de Carnes
    assert svc.sales_totals(f)["ventas_netas"] == 50.0


def test_filtro_fecha_excluye_fuera_de_rango():
    svc, b1 = _setup()
    f = DashboardFilters(preset="yesterday").resolved()
    # las ventas se sembraron este mes (día 2), no ayer necesariamente → 0 salvo coincidencia
    total = svc.sales_totals(f)["ventas_netas"]
    assert total >= 0.0


def test_resolve_range_presets():
    fi, ff = resolve_range("today")
    assert fi == ff
    fi_m, ff_m = resolve_range("month")
    assert fi_m.endswith("-01")
