"""PROD-19 repunte batch 1 — DiscountGuard lee costo canónico (Pricing), no productos."""

import inspect
import sqlite3

import pytest

from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from core.services.discount_guard import DiscountGuard


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.execute("INSERT INTO product_cost (id, product_id, branch_id, average_cost, "
              "average_cost_currency, cost_method) VALUES ('c1','p1','','62.5','MXN','AVERAGE')")
    c.commit()
    yield c
    c.close()


def test_get_costo_reads_canonical_product_cost(conn):
    guard = DiscountGuard(conn)
    assert guard._get_costo("p1") == 62.5


def test_get_costo_missing_returns_zero(conn):
    assert DiscountGuard(conn)._get_costo("nope") == 0.0


def test_source_has_no_productos_sql():
    src = inspect.getsource(DiscountGuard).lower()
    assert "from productos" not in src
    assert "select coalesce(precio_compra,0) from productos" not in src
