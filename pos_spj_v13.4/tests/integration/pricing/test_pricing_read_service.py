"""PRC-7 — PricingReadService (overview + listas + precios + costos + historial)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.pricing.queries.pricing_read_service import PricingReadService
from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import PriceListKind
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


def _seed(conn):
    repo = PricingRepository(conn)
    base = PriceList(code="BASE", name="Base", kind=PriceListKind.BASE)
    base.submit(); base.approve(approved_by_user_id="mgr"); base.activate()
    repo.save_list(base)
    draft = PriceList(code="PROMO", name="Promo", kind=PriceListKind.PROMOTIONAL)
    repo.save_list(draft)  # DRAFT
    pp = ProductPrice(price_list_id=base.id, product_id="p1", sale_price=_m(100),
                      min_price=_m(80))
    repo.save_price(pp)
    repo.save_volume(VolumePrice(product_price_id=pp.id, min_quantity=Decimal("10"),
                                 price=_m(80)))
    repo.save_cost(ProductCost(product_id="p1", average_cost=_m(60), last_cost=_m(62)))
    repo.log_cost_change(product_id="p1", branch_id=None, old_value=_m(58),
                         new_value=_m(60), operation_id="op1", user_id="u1")
    # fila bajo mínimo: sólo puede existir vía backfill (la entidad la prohíbe),
    # se inserta directo para ejercitar el KPI below_min.
    conn.execute("INSERT INTO product_price (id, price_list_id, product_id, branch_id, "
                 "sale_price, sale_price_currency, min_price, min_price_currency) "
                 "VALUES ('below1', ?, 'p2', '', '50', 'MXN', '60', 'MXN')", (base.id,))
    conn.commit()
    return base


def test_overview_counts(conn):
    _seed(conn)
    c = PricingReadService(conn).overview_counts()
    assert c["lists_active"] == 1 and c["lists_pending"] == 1
    assert c["priced"] == 2 and c["costed"] == 1
    assert c["volume_tiers"] == 1 and c["below_min"] == 1


def test_list_price_lists(conn):
    _seed(conn)
    rows = PricingReadService(conn).list_price_lists()
    codes = {r["code"] for r in rows}
    assert codes == {"BASE", "PROMO"}


def test_list_product_prices(conn):
    base = _seed(conn)
    rows = PricingReadService(conn).list_product_prices(list_id=base.id)
    p1 = next(r for r in rows if r["product_id"] == "p1")
    assert p1["sale_price"] == "100.0000"
    assert p1["list_code"] == "BASE" and p1["min_price"] == "80.0000"


def test_list_costs(conn):
    _seed(conn)
    rows = PricingReadService(conn).list_costs()
    assert rows[0]["product_id"] == "p1" and rows[0]["average_cost"] == "60.0000"
    assert rows[0]["cost_method"] == "AVERAGE"


def test_list_price_history(conn):
    _seed(conn)
    rows = PricingReadService(conn).list_price_history(product_id="p1")
    assert rows[0]["field"] == "cost" and rows[0]["new_value"] == "60.0000"


def test_product_prices_joins_products_when_present(conn):
    base = _seed(conn)
    conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, code TEXT, name TEXT, "
                 "name_normalized TEXT)")
    conn.execute("INSERT INTO products (id, code, name, name_normalized) "
                 "VALUES ('p1','A-1','Bistec','bistec')")
    conn.commit()
    rows = PricingReadService(conn).list_product_prices(query="bist")
    assert len(rows) == 1 and rows[0]["product_name"] == "Bistec"
