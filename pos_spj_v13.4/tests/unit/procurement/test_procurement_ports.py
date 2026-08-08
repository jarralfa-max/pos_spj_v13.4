"""FASE 2 — Crear puertos: ProcurementProductCatalogPort must let Compras
replace manual product-id typing with real search-and-select against the
canonical catalog, never the legacy ``productos`` table."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.procurement.adapters.product_catalog_adapter import (
    ProcurementProductCatalogAdapter,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def products_conn():
    conn = sqlite3.connect(":memory:")
    create_products_schema(conn)
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p1','COD-1','Pollo entero','INVENTORY','ACTIVE','KG',1,1)")
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p2','COD-2','Servicio de limpieza','SERVICE','ACTIVE','PZA',0,0)")
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, lifecycle_status,"
        " base_unit_id, purchasable, sellable) VALUES"
        " ('p3','COD-3','Producto descontinuado','INVENTORY','DISCONTINUED',"
        " 'PZA',1,0)")
    yield conn
    conn.close()


def test_search_finds_purchasable_products_by_name(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    results = adapter.search("Pollo")
    assert [r.product_id for r in results] == ["p1"]
    assert results[0].code == "COD-1" and results[0].purchase_unit == "KG"


def test_search_excludes_non_purchasable_and_discontinued_products(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.search("Servicio de limpieza") == []  # purchasable=0
    assert adapter.search("descontinuado") == []  # lifecycle_status != ACTIVE


def test_search_by_code(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    results = adapter.search("COD-1")
    assert [r.product_id for r in results] == ["p1"]


def test_search_with_blank_query_returns_nothing_never_the_whole_catalog(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.search("") == []
    assert adapter.search("   ") == []


def test_resolve_returns_active_product_by_id(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    option = adapter.resolve("p1")
    assert option is not None
    assert option.name == "Pollo entero" and option.purchasable is True


def test_resolve_returns_none_for_missing_or_discontinued_product(products_conn):
    adapter = ProcurementProductCatalogAdapter(products_conn)
    assert adapter.resolve("does-not-exist") is None
    assert adapter.resolve("p3") is None  # DISCONTINUED — never resolved as buyable
    assert adapter.resolve("") is None


def test_adapter_degrades_gracefully_when_products_schema_is_absent():
    """A caller on a connection without the products schema yet (an
    un-migrated install, or a narrow test fixture) gets an empty result,
    never a crash and never an invented product."""
    conn = sqlite3.connect(":memory:")
    adapter = ProcurementProductCatalogAdapter(conn)
    assert adapter.search("anything") == []
    assert adapter.resolve("anything") is None
    conn.close()
