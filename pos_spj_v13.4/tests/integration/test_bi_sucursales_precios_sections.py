"""PASS 6 — las secciones Sucursales y Precios de Inteligencia de Negocios.

Sus dos rutas (`bi_branches`, `bi_pricing`) abrían una página vacía. No les
faltaban datos: `BiSalesQueryService` ya calculaba venta por sucursal y margen
por categoría/producto, y nadie los mostraba.

LO QUE MÁS IMPORTA COMPROBAR AQUÍ
----------------------------------
`BiDashboardService.section_data()` resuelve la sección con
`getattr(self, f"_section_{section}", None)` y, si no encuentra el método,
DEVUELVE UNA ESTRUCTURA VACÍA en vez de fallar:

    {"section": ..., "title": ..., "kpis": [], "charts": [], "tables": []}

Es decir: una clave mal escrita en `_SECTION_KEY_BY_PAGE_ID` produce una página
que abre, se ve ordenada y no enseña nada — indistinguible de "no hubo ventas
este mes". Por eso estas pruebas afirman sobre VALORES concretos y no sobre que
la llamada no reviente.
"""
from __future__ import annotations

import pytest

from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import BiDashboardService
from tests.integration import bi_seed as S


def _servicio(conn):
    return BiDashboardService(BiDashboardQueryService(conn))


def _mes(conn, section):
    return _servicio(conn).section_data(section, DashboardFilters(preset="month"))


def _kpis(datos):
    return {k["title"]: k["value"] for k in datos["kpis"]}


@pytest.fixture
def conn():
    """Dos sucursales con venta desigual y dos productos con margen distinto.

    Desigual a propósito: con importes iguales, un error de agrupación o de
    orden no se notaría.
    """
    c = S.fresh_db()
    centro = S.add_branch(c, "Centro")
    norte = S.add_branch(c, "Norte")
    pollo = S.add_product(c, "Pollo", "Aves", 18.0, branch_id=centro)
    res = S.add_product(c, "Res", "Carnes", 60.0, branch_id=centro)
    dia = S.this_month_day()
    # Centro: 3 pollos a 30 (costo 18) + 1 res a 100 (costo 60) = 190
    S.add_sale(c, centro, [(pollo, 3, 30.0, 18.0), (res, 1, 100.0, 60.0)], when=dia)
    # Norte: 1 pollo a 30 = 30
    S.add_sale(c, norte, [(pollo, 1, 30.0, 18.0)], when=dia)
    c.commit()
    return c


# ── Sucursales ──────────────────────────────────────────────────────────────
def test_the_branch_section_is_not_the_silent_empty_fallback(conn):
    """Si la clave de sección no coincidiera con el método, esto pasaría con
    listas vacías y sin error."""
    datos = _mes(conn, "sucursales")
    assert datos["section"] == "sucursales"
    assert datos["kpis"] and datos["charts"] and datos["tables"]


def test_every_branch_with_sales_appears_with_its_own_total(conn):
    datos = _mes(conn, "sucursales")
    filas = {fila[0]: fila[1] for fila in datos["tables"][0]["rows"]}
    assert filas == {"Centro": "$190.00", "Norte": "$30.00"}


def test_the_branches_are_ordered_by_sales(conn):
    """Una comparativa que no ordena obliga a leerla entera para ver quién
    vende más, que es la única pregunta que se le hace."""
    datos = _mes(conn, "sucursales")
    assert [fila[0] for fila in datos["tables"][0]["rows"]] == ["Centro", "Norte"]


def test_concentration_is_the_share_of_the_biggest_branch(conn):
    """El dato que no se ve sumando columnas: 190 de 220 es el 86%, y que una
    sucursal cargue con eso es una dependencia, no un éxito."""
    kpis = _kpis(_mes(conn, "sucursales"))
    assert kpis["Venta total"] == 220.0
    assert kpis["Sucursales con venta"] == 2
    assert kpis["Concentración"] == pytest.approx(86.36, abs=0.01)


def test_concentration_is_flagged_when_one_branch_carries_more_than_half(conn):
    variantes = {k["title"]: k["variant"] for k in _mes(conn, "sucursales")["kpis"]}
    assert variantes["Concentración"] == "danger"


def test_a_period_without_sales_does_not_divide_by_zero(conn):
    """Sin ventas el total es cero, y el porcentaje de concentración se
    calcula dividiendo por él."""
    datos = _servicio(conn).section_data("sucursales", DashboardFilters(preset="today"))
    kpis = _kpis(datos)
    assert kpis["Venta total"] == 0
    assert kpis["Concentración"] == 0


# ── Precios ─────────────────────────────────────────────────────────────────
def test_the_pricing_section_is_not_the_silent_empty_fallback(conn):
    datos = _mes(conn, "precios")
    assert datos["section"] == "precios"
    assert datos["kpis"] and datos["charts"] and datos["tables"]


def test_margin_is_revenue_minus_cost(conn):
    """190 de ingreso contra 114 de costo (3×18 + 1×60) son 76 de margen."""
    kpis = _kpis(_mes(conn, "precios"))
    assert kpis["Ingresos"] == 220.0          # incluye la venta de Norte
    assert kpis["Margen"] == 220.0 - 132.0    # 132 = 4×18 + 1×60
    assert kpis["Margen %"] == pytest.approx(40.0, abs=0.01)


def test_each_product_carries_its_own_margin(conn):
    filas = {fila[0]: fila for fila in _mes(conn, "precios")["tables"][0]["rows"]}
    assert filas["Res"][5] == "$40.00"        # 100 - 60
    assert filas["Pollo"][5] == "$48.00"      # 4×30 - 4×18


def test_the_products_are_ordered_by_margin(conn):
    """La tabla existe para encontrar lo que menos deja; si no ordena, hay que
    leerla entera."""
    filas = [fila[0] for fila in _mes(conn, "precios")["tables"][0]["rows"]]
    assert filas == ["Pollo", "Res"]


def test_a_period_without_sales_does_not_divide_by_zero(conn):
    kpis = _kpis(_servicio(conn).section_data("precios", DashboardFilters(preset="today")))
    assert kpis["Ingresos"] == 0
    assert kpis["Margen %"] == 0


def test_no_product_is_judged_as_badly_priced(conn):
    """Marcar un producto como "mal precio" exige un margen objetivo, que es
    una regla de negocio que no está declarada en ninguna parte. La sección
    ordena y deja el juicio a quien lee — inventar el umbral aquí sería
    fabricar una política."""
    columnas = _mes(conn, "precios")["tables"][0]["columns"]
    assert not any("bajo" in c.lower() or "alerta" in c.lower() for c in columnas)


# ── el cableado de las rutas ────────────────────────────────────────────────
def test_both_routes_point_at_the_new_sections():
    """Un mapeo mal escrito no falla: da la estructura vacía de arriba."""
    from frontend.desktop.modules.business_intelligence.business_intelligence_routes import (
        _REAL_ROUTE_BUILDERS,
        _SECTION_KEY_BY_PAGE_ID,
    )

    assert _SECTION_KEY_BY_PAGE_ID["bi_branches"] == "sucursales"
    assert _SECTION_KEY_BY_PAGE_ID["bi_pricing"] == "precios"
    assert _REAL_ROUTE_BUILDERS["bi_branches"] == "_build_analytical_section"
    assert _REAL_ROUTE_BUILDERS["bi_pricing"] == "_build_analytical_section"


def test_every_mapped_section_key_has_a_real_builder():
    """La comprobación que protege a todas las secciones, no sólo a estas dos:
    cada clave mapeada tiene que existir como `_section_<clave>`."""
    from frontend.desktop.modules.business_intelligence.business_intelligence_routes import (
        _SECTION_KEY_BY_PAGE_ID,
    )

    faltan = [
        f"{page_id} -> _section_{clave}"
        for page_id, clave in _SECTION_KEY_BY_PAGE_ID.items()
        if not hasattr(BiDashboardService, f"_section_{clave}")
    ]
    assert not faltan, f"Secciones mapeadas sin método que las construya: {faltan}"
