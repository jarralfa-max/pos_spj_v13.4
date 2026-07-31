"""P0-B slice 4 — búsquedas canónicas para consumidores (§11).

POS/Compras/Inventario/Transferencias buscan productos canónicos por
capacidad/sucursal/canal SIN leer `productos` legacy ni conocer el UUID.
"""

import sqlite3

import pytest

from backend.application.products.queries.product_selection_query_service import (
    ProductSelectionDTO,
    SearchInventoryManagedProductsQueryService,
    SearchPurchasableProductsQueryService,
    SearchSellableProductsQueryService,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid


def _product(conn, *, name, code, sellable=1, purchasable=1, inventory_managed=1,
             internal_only=0, lifecycle="ACTIVE", ptype="RESALE_PRODUCT"):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed, "
        "internal_only) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pid, code, name, name.lower(), ptype, lifecycle, "kg", sellable, purchasable,
         inventory_managed, internal_only))
    return pid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    return c


def test_sellable_excludes_draft_and_internal(conn):
    _product(conn, name="Refresco", code="R1")                 # vendible ACTIVE
    _product(conn, name="Borrador", code="D1", lifecycle="DRAFT")
    _product(conn, name="Insumo interno", code="I1", internal_only=1, sellable=0)
    conn.commit()
    res = SearchSellableProductsQueryService(conn).search()
    names = {r.name for r in res}
    assert "Refresco" in names
    assert "Borrador" not in names and "Insumo interno" not in names
    assert all(isinstance(r, ProductSelectionDTO) for r in res)


def test_sellable_requires_branch_enabled_when_branch_given(conn):
    p1 = _product(conn, name="Con sucursal", code="C1")
    _product(conn, name="Sin sucursal", code="S1")
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled) "
                 "VALUES (?,?,?,1)", (new_uuid(), p1, "b1"))
    conn.commit()
    res = SearchSellableProductsQueryService(conn).search(branch_id="b1")
    names = {r.name for r in res}
    assert names == {"Con sucursal"}


def test_sellable_channel_assortment_filter(conn):
    p1 = _product(conn, name="En POS", code="P1")
    _product(conn, name="Fuera de POS", code="P2")
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled) "
                 "VALUES (?,?,?,1)", (new_uuid(), p1, "b1"))
    aid = new_uuid()
    conn.execute("INSERT INTO assortments (id, name, channel, branch_id, active) "
                 "VALUES (?,?,?,?,1)", (aid, "Surtido POS", "POS", "b1"))
    conn.execute("INSERT INTO assortment_products (id, assortment_id, product_id, enabled) "
                 "VALUES (?,?,?,1)", (new_uuid(), aid, p1))
    conn.commit()
    res = SearchSellableProductsQueryService(conn).search(branch_id="b1", channel_id="POS")
    assert {r.name for r in res} == {"En POS"}


def test_purchasable_and_inventory_capability_filters(conn):
    _product(conn, name="Comprable", code="X1", purchasable=1, inventory_managed=0)
    _product(conn, name="Inventariable", code="X2", purchasable=0, inventory_managed=1)
    conn.commit()
    pur = {r.name for r in SearchPurchasableProductsQueryService(conn).search()}
    inv = {r.name for r in SearchInventoryManagedProductsQueryService(conn).search()}
    assert "Comprable" in pur and "Inventariable" not in pur
    assert "Inventariable" in inv and "Comprable" not in inv


def test_query_and_pagination(conn):
    for i in range(5):
        _product(conn, name=f"Pollo {i}", code=f"K{i}")
    _product(conn, name="Res", code="RS1")
    conn.commit()
    svc = SearchSellableProductsQueryService(conn)
    assert {r.name for r in svc.search(query="Pollo")} == {f"Pollo {i}" for i in range(5)}
    page = svc.search(query="Pollo", limit=2, offset=0)
    assert len(page) == 2
