"""P0-B slice 6 — el catálogo POS lee canónico (products + satélites), no `productos`.

Caracteriza `ProductCatalogQueryService` tras el repunte: preserva el contrato de
salida que consume `modulos/ventas.py` pero compone el maestro canónico `products`
con precio (product_price BASE), existencia (inventory_balances), categoría, stock
mínimo (inventory_replenishment_rule), imagen y código de barras canónicos, y mapea
es_compuesto = bundle_allowed OR recipe_allowed y es_subproducto = product_type ∈
{BY_PRODUCT, CO_PRODUCT}.
"""

import sqlite3

import pytest

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid
from core.services.sales.product_catalog_query_service import ProductCatalogQueryService

_BRANCH = "1"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    # lista BASE de precios
    c.execute("INSERT INTO price_list (id, code, name, kind, status) "
              "VALUES ('pl-base','BASE','Base','SALE','ACTIVE')")
    c.commit()
    return c


def _product(c, *, pid, name, code, ptype="RESALE_PRODUCT", bundle=0, recipe=0,
             internal=0, unit="kg", category_id=None, lifecycle="ACTIVE"):
    c.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, category_id, sellable, purchasable, "
        "inventory_managed, internal_only, bundle_allowed, recipe_allowed) "
        "VALUES (?,?,?,?,?,?,?,?,1,1,1,?,?,?)",
        (pid, code, name, name.lower(), ptype, lifecycle, unit, category_id, internal,
         bundle, recipe))


def _price(c, pid, amount):
    c.execute("INSERT INTO product_price (id, price_list_id, product_id, branch_id, "
              "sale_price) VALUES (?,?,?,'',?)", (new_uuid(), "pl-base", pid, str(amount)))


def _balance(c, pid, qty, reserved=0):
    c.execute("INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
              "location_id, lot_id, inventory_status, quantity, reserved_quantity, "
              "updated_at) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
              (new_uuid(), pid, _BRANCH, "w1", "", "", "AVAILABLE", str(qty), str(reserved)))


def test_catalog_dict_contract_is_canonical(conn):
    conn.execute("INSERT INTO product_categories (id, code, name, name_normalized, active) "
                 "VALUES ('cat1','CARN','Carnes','carnes',1)")
    _product(conn, pid="p1", name="Pollo", code="C1", category_id="cat1")
    _price(conn, "p1", "100")
    _balance(conn, "p1", "10")
    conn.execute("INSERT INTO inventory_replenishment_rule (id, product_id, branch_id, "
                 "warehouse_id, basis, min_quantity, reorder_point, created_at) "
                 "VALUES (?,?,'','','MIN_MAX','3','3',datetime('now'))", (new_uuid(), "p1"))
    conn.execute("INSERT INTO product_barcodes (id, product_id, barcode_value, "
                 "barcode_type, is_primary, active) VALUES (?,?,?,?,1,1)",
                 (new_uuid(), "p1", "CB1", "EAN13"))
    conn.execute("INSERT INTO product_images (id, product_id, uri, is_primary, sort_order) "
                 "VALUES (?,?,?,1,0)", (new_uuid(), "p1", "/img/p1.png"))
    conn.commit()

    rows = ProductCatalogQueryService(conn).list_visible_products(branch_id=_BRANCH)
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "p1" and r["nombre"] == "Pollo" and r["codigo"] == "C1"
    assert r["precio"] == 100.0 and r["existencia"] == 10.0
    assert r["unidad"] == "kg" and r["categoria"] == "Carnes"
    assert r["stock_minimo"] == 3.0 and r["imagen_path"] == "/img/p1.png"
    assert r["codigo_barras"] == "CB1"
    assert r["es_compuesto"] == 0 and r["es_subproducto"] == 0


def test_compound_and_byproduct_flags_mapped(conn):
    _product(conn, pid="combo", name="Combo", code="K1", bundle=1)
    _product(conn, pid="rec", name="Receta", code="R1", recipe=1)
    _product(conn, pid="sub", name="Subproducto", code="S1", ptype="BY_PRODUCT")
    for pid in ("combo", "rec", "sub"):
        _price(conn, pid, "10")
        _balance(conn, pid, "5")
    conn.commit()
    rows = {r["id"]: r for r in
            ProductCatalogQueryService(conn).list_visible_products(branch_id=_BRANCH)}
    assert rows["combo"]["es_compuesto"] == 1
    assert rows["rec"]["es_compuesto"] == 1
    assert rows["sub"]["es_subproducto"] == 1


def test_excludes_draft_and_internal(conn):
    _product(conn, pid="ok", name="OK", code="OK1")
    _product(conn, pid="draft", name="Borrador", code="D1", lifecycle="DRAFT")
    _product(conn, pid="int", name="Interno", code="I1", internal=1)
    conn.commit()
    names = {r["nombre"] for r in
             ProductCatalogQueryService(conn).list_visible_products(branch_id=_BRANCH)}
    assert names == {"OK"}


def test_barcode_lookup_and_categories(conn):
    conn.execute("INSERT INTO product_categories (id, code, name, name_normalized, active) "
                 "VALUES ('c1','B','Bebidas','bebidas',1)")
    _product(conn, pid="p1", name="Agua", code="A1", category_id="c1")
    _price(conn, "p1", "12")
    _balance(conn, "p1", "7")
    conn.execute("INSERT INTO product_barcodes (id, product_id, barcode_value, "
                 "barcode_type, is_primary, active) VALUES (?,?,?,?,1,1)",
                 (new_uuid(), "p1", "750777", "EAN13"))
    conn.commit()
    svc = ProductCatalogQueryService(conn)
    found = svc.get_product_by_barcode(_BRANCH, "750777")
    assert found and found["nombre"] == "Agua"
    assert svc.get_categories() == ["Bebidas"]
