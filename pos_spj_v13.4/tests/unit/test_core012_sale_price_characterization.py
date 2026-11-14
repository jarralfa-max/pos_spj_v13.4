"""CARACTERIZACIÓN (SDLC-CORE-012): precio que se cobra, tal como funciona HOY.

Estas pruebas NO dicen que el comportamiento sea correcto: lo fijan para que un
cambio se haga a propósito. La marca `CAMBIA: <ítem>` indica qué ítem debe
actualizarlas al corregirlo; lo demás es comportamiento que debe conservarse.
"""
from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.pricing_resolution import resolve_sale_price
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_pricing_client import SalesPricingClient
from backend.shared.ids import new_uuid


class _Motor:
    def __init__(self, *, price=None, error=None) -> None:
        self.price, self.error, self.calls = price, error, []

    def effective_price(self, product_id, **kwargs):
        self.calls.append((product_id, kwargs))
        if self.error is not None:
            raise self.error
        return self.price


def _m(valor: str) -> Money:
    return Money(Decimal(valor))


# ── resolve_sale_price ──────────────────────────────────────────────────────
def test_without_an_engine_there_is_no_price():
    assert resolve_sale_price(None, branch_id="b", customer_id=None, product_id="p",
                              quantity=Decimal("1")) is None


def test_the_engine_receives_branch_customer_and_quantity():
    motor = _Motor(price=Decimal("88.50"))
    precio = resolve_sale_price(motor, branch_id="b", customer_id="c", product_id="p",
                                quantity=Decimal("3"))
    assert precio == Decimal("88.50")
    assert motor.calls == [("p", {"branch_id": "b", "customer_id": "c",
                                  "quantity": Decimal("3")})]


def test_an_engine_exception_is_swallowed_and_logged(caplog):
    """CARACTERIZACIÓN — CAMBIA: SDLC-SALES-001. Hoy la excepción no sube: se
    registra y se responde None, igual que "sin precio"."""
    with caplog.at_level(logging.ERROR, logger="spj.sales.pricing"):
        precio = resolve_sale_price(_Motor(error=RuntimeError("motor caído")), branch_id="b",
                                    customer_id=None, product_id="p", quantity=Decimal("1"))
    assert precio is None
    assert "se usa el del catálogo" in caplog.text


# ── carrito ─────────────────────────────────────────────────────────────────
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_pricing_schema(c)
    c.commit()
    yield c
    c.close()


def _agregar(conn, motor, *, catalogo="50.00"):
    auth = SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())
    cajero = new_uuid()
    sale_id = StartSaleUseCase(auth).execute(
        conn, branch_id=new_uuid(), cashier_user_id=cajero, operation_id=new_uuid(),
        actor_user_id=cajero).entity_id
    resultado = AddSaleLineUseCase(auth, pricing=motor).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("2"),
        unit_price=Decimal(catalogo), actor_user_id=cajero, operation_id=new_uuid())
    assert resultado.success, resultado.message
    return SaleRepository(conn).get(sale_id).lines[0]


def test_an_engine_failure_charges_the_catalog_price_silently(conn):
    """CARACTERIZACIÓN — CAMBIA: SDLC-SALES-001 (defecto conocido). El motor falla,
    la línea se agrega al precio de catálogo y sólo la marca del snapshot lo dice."""
    linea = _agregar(conn, _Motor(error=RuntimeError("motor caído")))
    assert linea.unit_price == Decimal("50.00")
    assert linea.product_snapshot["price_source"] == "CATALOG"


def test_a_product_without_a_price_also_falls_to_the_catalog(conn):
    """CARACTERIZACIÓN — CAMBIA: SDLC-SALES-001, si separa "sin precio" de "falló"."""
    linea = _agregar(conn, _Motor(price=None))
    assert linea.unit_price == Decimal("50.00")
    assert linea.product_snapshot["price_source"] == "CATALOG"


def test_the_engine_price_beats_the_catalog_price(conn):
    linea = _agregar(conn, _Motor(price=Decimal("44.00")))
    assert linea.unit_price == Decimal("44.00")
    assert linea.product_snapshot["price_source"] == "PRICING"


# ── motor real: base / canal / cliente / volumen ────────────────────────────
def _lista(repo, kind, code, **extra):
    lista = PriceList(code=code, name=code, kind=kind, **extra)
    lista.submit()
    lista.approve(approved_by_user_id="mgr")
    lista.activate()
    repo.save_list(lista)
    return lista


@pytest.fixture
def precios(conn):
    repo = PricingRepository(conn)
    base = _lista(repo, PriceListKind.BASE, "BASE")
    repo.save_price(ProductPrice(price_list_id=base.id, product_id="p", sale_price=_m("100.00")))
    return conn, repo


def test_the_base_list_prices_the_pos(precios):
    conn, _repo = precios
    assert SalesPricingClient(conn).effective_price("p") == Decimal("100.00")


def test_a_channel_list_only_applies_on_its_own_channel(precios):
    conn, repo = precios
    canal = _lista(repo, PriceListKind.CHANNEL, "WA", channel="WHATSAPP")
    repo.save_price(ProductPrice(price_list_id=canal.id, product_id="p", sale_price=_m("120.00")))
    cliente = SalesPricingClient(conn)
    assert cliente.effective_price("p") == Decimal("100.00")                       # POS
    assert cliente.effective_price("p", channel="WHATSAPP") == Decimal("120.00")


def test_a_customer_list_beats_the_base_list(precios):
    conn, repo = precios
    lista = _lista(repo, PriceListKind.CUSTOMER, "VIP")
    repo.save_price(ProductPrice(price_list_id=lista.id, product_id="p", sale_price=_m("90.00")))
    repo.assign_customer_list("c1", lista.id)
    cliente = SalesPricingClient(conn)
    assert cliente.effective_price("p", customer_id="c1") == Decimal("90.00")
    assert cliente.effective_price("p", customer_id="c2") == Decimal("100.00")


def test_a_volume_tier_beats_the_list_from_its_minimum_quantity(precios):
    conn, repo = precios
    base = repo.active_list_of_kind(PriceListKind.BASE)
    precio = repo.effective_price(price_list_id=base.id, product_id="p", branch_id=None,
                                  on_date="2099-01-01")
    repo.save_volume(VolumePrice(product_price_id=precio.id, min_quantity=Decimal("10"),
                                 price=_m("80.00")))
    cliente = SalesPricingClient(conn)
    assert cliente.effective_price("p", quantity=Decimal("9")) == Decimal("100.00")
    assert cliente.effective_price("p", quantity=Decimal("10")) == Decimal("80.00")
