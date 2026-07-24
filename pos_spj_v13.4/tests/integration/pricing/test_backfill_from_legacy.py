"""PRC-5 — backfill legacy → Pricing/Costing (mapeo, Decimal, idempotencia)."""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.pricing.queries.product_price_query_service import (
    ProductCostQueryService,
    ProductPriceQueryService,
)
from backend.domain.pricing.enums import PriceSource
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema

_mig = importlib.import_module("migrations.standalone.150_pricing_backfill_from_legacy")


def _legacy_schema(c):
    c.execute("""
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, codigo TEXT, nombre TEXT, precio REAL,
            precio_compra REAL, precio_minimo_venta REAL, precio_minimo REAL,
            costo_promedio REAL, existencia REAL)
    """)
    c.execute("""
        CREATE TABLE listas_precio (
            id TEXT PRIMARY KEY, nombre TEXT, descripcion TEXT,
            descuento_global REAL, hereda_de TEXT, activa INTEGER)
    """)
    c.execute("CREATE TABLE precios_lista (lista_id TEXT, producto_id TEXT, precio REAL, "
              "PRIMARY KEY(lista_id, producto_id))")
    c.execute("""
        CREATE TABLE precios_volumen (
            id TEXT PRIMARY KEY, producto_id TEXT, lista_id TEXT,
            cantidad_min REAL, precio REAL, unidad TEXT)
    """)
    c.execute("CREATE TABLE clientes_lista_precio (cliente_id TEXT PRIMARY KEY, lista_id TEXT)")
    c.execute("""
        CREATE TABLE branch_products (
            branch_id TEXT, producto_id TEXT, precio_local REAL)
    """)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    _legacy_schema(c)
    c.commit()
    yield c
    c.close()


def _prod(c, **kw):
    base = dict(id="p1", codigo="A-1", nombre="Bistec", precio=100.0, precio_compra=60.0,
                precio_minimo_venta=80.0, precio_minimo=0.0, costo_promedio=62.5,
                existencia=10.0)
    base.update(kw)
    cols = ",".join(base)
    ph = ",".join("?" for _ in base)
    c.execute(f"INSERT INTO productos ({cols}) VALUES ({ph})", tuple(base.values()))


def test_base_price_backfilled(conn):
    _prod(conn)
    _mig.run(conn)
    r = ProductPriceQueryService(conn).get_sale_price("p1")
    assert r.source is PriceSource.BASE and r.price.amount == Decimal("100")
    assert r.min_price.amount == Decimal("80")


def test_cost_backfilled_decimal(conn):
    _prod(conn)
    _mig.run(conn)
    cost = ProductCostQueryService(conn).get_average_cost("p1")
    assert cost.amount == Decimal("62.5")
    # sin costo promedio → usa precio de compra como promedio inicial
    _prod(conn, id="p2", codigo="A-2", costo_promedio=0.0, precio_compra=40.0)
    _mig.run(conn)
    assert ProductCostQueryService(conn).get_average_cost("p2").amount == Decimal("40")


def test_no_real_columns_in_pricing(conn):
    _prod(conn)
    _mig.run(conn)
    for table in ("product_price", "product_cost", "volume_price"):
        types = {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "REAL" not in types.values()


def test_zero_price_skipped(conn):
    _prod(conn, id="z1", codigo="Z-1", precio=0.0)
    _mig.run(conn)
    assert ProductPriceQueryService(conn).get_sale_price("z1").source is PriceSource.NONE


def test_customer_list_and_volume_backfilled(conn):
    _prod(conn)
    conn.execute("INSERT INTO listas_precio (id, nombre, descuento_global, activa) "
                 "VALUES ('L1','Mayoreo',0,1)")
    conn.execute("INSERT INTO precios_lista (lista_id, producto_id, precio) VALUES ('L1','p1',85.0)")
    conn.execute("INSERT INTO precios_volumen (id, producto_id, lista_id, cantidad_min, precio) "
                 "VALUES ('v1','p1','L1',10.0,70.0)")
    conn.execute("INSERT INTO clientes_lista_precio (cliente_id, lista_id) VALUES ('c1','L1')")
    _mig.run(conn)
    svc = ProductPriceQueryService(conn)
    r = svc.get_sale_price("p1", customer_id="c1")
    assert r.source is PriceSource.CUSTOMER_LIST and r.price.amount == Decimal("85")
    r2 = svc.get_sale_price("p1", customer_id="c1", quantity=Decimal("12"))
    assert r2.source is PriceSource.VOLUME and r2.price.amount == Decimal("70")


def test_list_discount_backfilled(conn):
    _prod(conn)
    conn.execute("INSERT INTO listas_precio (id, nombre, descuento_global, activa) "
                 "VALUES ('L1','Promo',10,1)")
    conn.execute("INSERT INTO precios_lista (lista_id, producto_id, precio) VALUES ('L1','p1',100.0)")
    conn.execute("INSERT INTO clientes_lista_precio (cliente_id, lista_id) VALUES ('c1','L1')")
    _mig.run(conn)
    r = ProductPriceQueryService(conn).get_sale_price("p1", customer_id="c1")
    assert r.price.amount == Decimal("90")  # 100 - 10%


def test_branch_price_override_backfilled(conn):
    _prod(conn)
    conn.execute("INSERT INTO branch_products (branch_id, producto_id, precio_local) "
                 "VALUES ('b1','p1',95.0)")
    _mig.run(conn)
    svc = ProductPriceQueryService(conn)
    assert svc.get_sale_price("p1", branch_id="b1").price.amount == Decimal("95")
    assert svc.get_sale_price("p1", branch_id="b2").price.amount == Decimal("100")


def test_idempotent(conn):
    _prod(conn)
    conn.execute("INSERT INTO listas_precio (id, nombre, descuento_global, activa) "
                 "VALUES ('L1','Mayoreo',0,1)")
    conn.execute("INSERT INTO precios_lista (lista_id, producto_id, precio) VALUES ('L1','p1',85.0)")
    conn.execute("INSERT INTO precios_volumen (id, producto_id, lista_id, cantidad_min, precio) "
                 "VALUES ('v1','p1','L1',10.0,70.0)")
    _mig.run(conn)
    _mig.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM product_price").fetchone()[0] == 2  # base + lista
    assert conn.execute("SELECT COUNT(*) FROM volume_price").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM price_list").fetchone()[0] == 2  # BASE + L1
    assert conn.execute("SELECT COUNT(*) FROM product_cost").fetchone()[0] == 1
