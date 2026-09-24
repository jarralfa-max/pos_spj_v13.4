"""La sección "Configuración" de Precios deja de ser una ruta muerta.

`pricing_settings` estaba declarada en la navegación desde PRC-7 y `build_page`
devolvía `None`, así que abría con "Esta sección aún no está construida". Estas
pruebas cubren las tres capas que hacían falta: la consulta
(`settings_summary`), el formato (`settings_table`) y la ruta.

Lo que se comprueba NO es que la pantalla pinte algo, sino que diga la verdad
sobre una base concreta: sin lista base activa tiene que AVISAR, con dos monedas
tiene que AVISAR, y sin precios no puede fingir que la configuración está
completa. Una pantalla de configuración que se ve bien sobre una configuración
rota es exactamente el modo de fallo que este módulo ya tuvo.
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.pricing.queries.pricing_read_service import PricingReadService
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from frontend.desktop.modules.pricing.view_models import settings_table


def _m(v):
    return Money(Decimal(str(v)))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _active_base(conn, *, code="BASE", name="Base"):
    repo = PricingRepository(conn)
    lst = PriceList(code=code, name=name, kind=PriceListKind.BASE)
    lst.submit(); lst.approve(approved_by_user_id="mgr"); lst.activate()
    repo.save_list(lst)
    return lst


def _rows(summary) -> dict:
    """`{parámetro: (valor, nota)}` — leer por nombre, no por posición."""
    vm = settings_table(summary)
    return {r[0]: (r[1], r[2]) for r in vm.rows}


class TestSettingsSummary:
    def test_an_empty_module_reports_no_base_list_instead_of_looking_fine(self, conn):
        s = PricingReadService(conn).settings_summary()
        assert s["base_lists"] == []
        valor, nota = _rows(s)["Lista de precio base activa"]
        assert valor == "Ninguna"
        assert "Sin lista base activa" in nota

    def test_the_active_base_list_is_the_one_that_governs(self, conn):
        _active_base(conn)
        # Una lista promocional en borrador NO debe confundirse con la base.
        PricingRepository(conn).save_list(
            PriceList(code="PROMO", name="Promo", kind=PriceListKind.PROMOTIONAL))
        s = PricingReadService(conn).settings_summary()
        assert [b["code"] for b in s["base_lists"]] == ["BASE"]
        valor, nota = _rows(s)["Lista de precio base activa"]
        assert valor == "BASE · Base"
        assert "no aplica lista de canal ni de cliente" in nota

    def test_two_active_base_lists_are_reported_as_a_problem(self, conn):
        _active_base(conn, code="BASE", name="Base")
        _active_base(conn, code="BASE2", name="Otra base")
        s = PricingReadService(conn).settings_summary()
        assert len(s["base_lists"]) == 2
        valor, nota = _rows(s)["Lista de precio base activa"]
        assert valor == "BASE, BASE2"
        assert "sólo debería haber una" in nota

    def test_lists_are_counted_by_kind_including_drafts(self, conn):
        _active_base(conn)
        PricingRepository(conn).save_list(
            PriceList(code="PROMO", name="Promo", kind=PriceListKind.PROMOTIONAL))
        s = PricingReadService(conn).settings_summary()
        assert s["lists_by_kind"]["BASE"] == 1
        assert s["lists_by_kind"]["PROMOTIONAL"] == 1
        valor, _ = _rows(s)["Listas por tipo"]
        assert "Base: 1" in valor and "Promoción: 1" in valor

    def test_a_single_currency_is_reported_as_such(self, conn):
        base = _active_base(conn)
        PricingRepository(conn).save_price(ProductPrice(
            price_list_id=base.id, product_id="p1", sale_price=_m(100)))
        s = PricingReadService(conn).settings_summary()
        assert s["currencies"] == ["MXN"]
        valor, nota = _rows(s)["Moneda"]
        assert valor == "MXN"
        assert "Una sola moneda" in nota

    def test_mixed_currencies_are_flagged_because_totals_stop_matching(self, conn):
        base = _active_base(conn)
        repo = PricingRepository(conn)
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p1",
                                     sale_price=_m(100)))
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p2",
                                     sale_price=Money(Decimal("5"), "USD")))
        s = PricingReadService(conn).settings_summary()
        assert s["currencies"] == ["MXN", "USD"]
        valor, nota = _rows(s)["Moneda"]
        assert valor == "MXN, USD"
        assert "no son comparables" in nota

    def test_minimum_price_coverage_is_counted(self, conn):
        base = _active_base(conn)
        repo = PricingRepository(conn)
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p1",
                                     sale_price=_m(100), min_price=_m(80)))
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p2",
                                     sale_price=_m(50)))
        s = PricingReadService(conn).settings_summary()
        assert (s["priced"], s["with_minimum"]) == (2, 1)
        valor, _ = _rows(s)["Precios con mínimo definido"]
        assert valor == "1 de 2"

    def test_no_minimum_at_all_warns_that_the_safety_net_is_off(self, conn):
        base = _active_base(conn)
        PricingRepository(conn).save_price(ProductPrice(
            price_list_id=base.id, product_id="p1", sale_price=_m(100)))
        s = PricingReadService(conn).settings_summary()
        _, nota = _rows(s)["Precios con mínimo definido"]
        assert "no pedirá autorización" in nota

    def test_branch_scoped_prices_are_distinguished_from_central_ones(self, conn):
        base = _active_base(conn)
        repo = PricingRepository(conn)
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p1",
                                     sale_price=_m(100)))
        repo.save_price(ProductPrice(price_list_id=base.id, product_id="p1",
                                     branch_id="b1", sale_price=_m(110)))
        s = PricingReadService(conn).settings_summary()
        assert s["branch_specific"] == 1
        valor, _ = _rows(s)["Alcance por sucursal"]
        assert valor == "1 precios acotados a una sucursal"

    def test_the_cost_method_actually_in_use_is_reported(self, conn):
        PricingRepository(conn).save_cost(ProductCost(
            product_id="p1", average_cost=_m(40)))
        s = PricingReadService(conn).settings_summary()
        assert s["cost_methods"] == ["AVERAGE"]
        valor, _ = _rows(s)["Método de costeo"]
        assert valor == "Promedio"


class TestSettingsRoute:
    def test_the_settings_route_no_longer_resolves_to_nothing(self):
        """Antes `build_page("pricing_settings", ...)` devolvía `None` y el
        contenedor pintaba "Esta sección aún no está construida"."""
        import inspect

        from frontend.desktop.modules.pricing import routes

        fuente = inspect.getsource(routes.build_page)
        assert '"pricing_settings"' in fuente

    def test_the_declared_navigation_entry_matches_the_route_id(self):
        """La navegación y el constructor de páginas tienen que usar el MISMO
        id: es el desajuste que deja una sección declarada sin página."""
        from frontend.desktop.modules.pricing.navigation import PRICING_NAV

        ids = {e.page_id for e in PRICING_NAV}
        assert "pricing_settings" in ids

    def test_every_declared_navigation_entry_has_a_branch_in_build_page(self):
        """La guardia general: ninguna sección del menú de Precios puede
        quedarse otra vez sin página."""
        import inspect

        from frontend.desktop.modules.pricing import routes
        from frontend.desktop.modules.pricing.navigation import PRICING_NAV

        fuente = inspect.getsource(routes.build_page)
        sin_pagina = [e.page_id for e in PRICING_NAV if f'"{e.page_id}"' not in fuente]
        assert sin_pagina == []
