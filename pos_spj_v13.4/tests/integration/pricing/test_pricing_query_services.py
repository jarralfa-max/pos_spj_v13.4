"""PRC-4 — query services + repositorio: precio resuelto y costo canónico."""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.pricing.queries.product_price_query_service import (
    ProductCostQueryService,
    ProductPriceQueryService,
)
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import PriceListKind, PriceSource
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.repositories.pricing.pricing_repository import (
    PricingRepository,
)
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema


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


def _active_base_list(repo):
    pl = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
    pl.submit(); pl.approve(approved_by_user_id="mgr"); pl.activate()
    repo.save_list(pl)
    return pl


def test_base_price(conn):
    repo = PricingRepository(conn)
    pl = _active_base_list(repo)
    repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1",
                                 sale_price=_m(25), min_price=_m(20)))
    r = ProductPriceQueryService(conn).get_sale_price("p1")
    assert r.source is PriceSource.BASE and r.price.amount == Decimal("25")


def test_branch_price_overrides_all_branches(conn):
    repo = PricingRepository(conn)
    pl = _active_base_list(repo)
    repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1", sale_price=_m(25)))
    repo.save_price(ProductPrice(price_list_id=pl.id, product_id="p1", branch_id="b1",
                                 sale_price=_m(22)))
    assert ProductPriceQueryService(conn).get_sale_price("p1", branch_id="b1").price.amount \
        == Decimal("22")
    assert ProductPriceQueryService(conn).get_sale_price("p1", branch_id="b2").price.amount \
        == Decimal("25")


def test_customer_list_wins(conn):
    repo = PricingRepository(conn)
    base = _active_base_list(repo)
    repo.save_price(ProductPrice(price_list_id=base.id, product_id="p1", sale_price=_m(25)))
    cust = PriceList(code="MAYOREO", name="Mayoreo", kind=PriceListKind.CUSTOMER)
    cust.submit(); cust.approve(approved_by_user_id="mgr"); cust.activate()
    repo.save_list(cust)
    repo.save_price(ProductPrice(price_list_id=cust.id, product_id="p1", sale_price=_m(20)))
    repo.assign_customer_list("cli1", cust.id)
    r = ProductPriceQueryService(conn).get_sale_price("p1", customer_id="cli1")
    assert r.source is PriceSource.CUSTOMER_LIST and r.price.amount == Decimal("20")


def test_volume_tier_wins(conn):
    repo = PricingRepository(conn)
    base = _active_base_list(repo)
    pp = ProductPrice(price_list_id=base.id, product_id="p1", sale_price=_m(25))
    repo.save_price(pp)
    repo.save_volume(VolumePrice(product_price_id=pp.id, min_quantity=Decimal("10"),
                                 price=_m(18)))
    r = ProductPriceQueryService(conn).get_sale_price("p1", quantity=Decimal("12"))
    assert r.source is PriceSource.VOLUME and r.price.amount == Decimal("18")
    # bajo el umbral → precio base
    r2 = ProductPriceQueryService(conn).get_sale_price("p1", quantity=Decimal("5"))
    assert r2.source is PriceSource.BASE


def test_below_minimum_flag(conn):
    repo = PricingRepository(conn)
    base = _active_base_list(repo)
    pp = ProductPrice(price_list_id=base.id, product_id="p1", sale_price=_m(25),
                      min_price=_m(20))
    repo.save_price(pp)
    repo.save_volume(VolumePrice(product_price_id=pp.id, min_quantity=Decimal("10"),
                                 price=_m(15)))
    r = ProductPriceQueryService(conn).get_sale_price("p1", quantity=Decimal("12"))
    assert r.below_minimum and r.price.amount == Decimal("15")


def test_no_price_returns_none(conn):
    r = ProductPriceQueryService(conn).get_sale_price("nope")
    assert r.price is None and r.source is PriceSource.NONE


def test_cost_query(conn):
    repo = PricingRepository(conn)
    repo.save_cost(ProductCost(product_id="p1", average_cost=_m(12.5)))
    conn.commit()
    assert ProductCostQueryService(conn).get_average_cost("p1").amount == Decimal("12.5")
    assert ProductCostQueryService(conn).get_average_cost("nope") is None
