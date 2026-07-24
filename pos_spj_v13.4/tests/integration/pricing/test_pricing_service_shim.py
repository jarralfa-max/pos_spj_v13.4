"""PRC-8 — el shim legacy pricing_service delega en el canónico (sin tablas legacy)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import PriceListKind
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from core.services.pricing_service import PricingService


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


def _seed(conn):
    repo = PricingRepository(conn)
    base = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
    base.submit(); base.approve(approved_by_user_id="mgr"); base.activate()
    repo.save_list(base)
    pp = ProductPrice(price_list_id=base.id, product_id="p1", sale_price=_m(100))
    repo.save_price(pp)
    repo.save_volume(VolumePrice(product_price_id=pp.id, min_quantity=Decimal("10"),
                                 price=_m(80)))
    cust = PriceList(code="MAYOREO", name="Mayoreo", kind=PriceListKind.CUSTOMER)
    cust.submit(); cust.approve(approved_by_user_id="mgr"); cust.activate()
    repo.save_list(cust)
    repo.save_price(ProductPrice(price_list_id=cust.id, product_id="p1", sale_price=_m(90)))
    repo.assign_customer_list("cli1", cust.id)
    conn.commit()


def test_base_price_marks_fuente_base(conn):
    _seed(conn)
    r = PricingService(conn).get_precio("p1")
    assert r["fuente"] == "base" and r["precio"] == 100.0


def test_customer_list_overrides(conn):
    _seed(conn)
    r = PricingService(conn).get_precio("p1", cliente_id="cli1")
    assert r["fuente"] == "customer_list" and r["precio"] == 90.0


def test_volume_overrides(conn):
    _seed(conn)
    r = PricingService(conn).get_precio("p1", cantidad=12)
    assert r["fuente"] == "volume" and r["precio"] == 80.0


def test_unknown_product_base_zero(conn):
    r = PricingService(conn).get_precio("nope")
    assert r["fuente"] == "base" and r["precio"] == 0.0


def test_shim_has_no_management_methods():
    # métodos muertos eliminados (código muerto, sin consumidores)
    for dead in ("set_precio_lista", "set_precio_volumen", "asignar_lista_cliente",
                 "get_listas", "get_precios_producto"):
        assert not hasattr(PricingService, dead)


def test_shim_source_has_no_legacy_price_sql():
    import inspect
    src = inspect.getsource(PricingService).lower()
    for token in ("from precios_lista", "from precios_volumen", "from listas_precio",
                  "from clientes_lista_precio", "select precio from productos"):
        assert token not in src
