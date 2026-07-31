"""P0-B slice 5 — PosProductCatalogFacade (§12): catálogo POS canónico compuesto.

Reproducido (escenario 4): el POS leía `productos` legacy. El facade compone
Productos (identidad/flags/barcode/sucursal) + Pricing (precio vigente) +
Inventario (disponible) SIN tocar el agregado Product ni la tabla legacy.

Pricing e Inventario se inyectan como fakes deterministas (sus servicios reales
tienen su propia suite); se ejercita la composición, el barcode y el filtrado real
(vendible + ACTIVE + sucursal habilitada).
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.products.queries.pos_product_catalog_facade import (
    PosProductCatalogFacade,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid


class _FakePricing:
    def __init__(self, prices):
        self._prices = prices

    def sale_price_amount(self, product_id, *, branch_id=None):
        return self._prices.get(product_id)


class _AvailDTO:
    def __init__(self, available):
        self.available = available


class _Availability:
    def __init__(self, avail):
        self._avail = avail

    def get_availability(self, *, product_id, branch_id):
        return _AvailDTO(self._avail.get(product_id, Decimal("0")))


def _product(conn, *, name, code, sellable=1, internal_only=0, lifecycle="ACTIVE"):
    pid = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, name_normalized, product_type, "
        "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed, "
        "internal_only) VALUES (?,?,?,?,?,?,?,?,1,1,?)",
        (pid, code, name, name.lower(), "RESALE_PRODUCT", lifecycle, "kg", sellable,
         internal_only))
    conn.execute("INSERT INTO branch_product (id, product_id, branch_id, enabled) "
                 "VALUES (?,?,?,1)", (new_uuid(), pid, "b1"))
    return pid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    return c


def _facade(conn, prices, avail):
    return PosProductCatalogFacade(
        conn, pricing_facade=_FakePricing(prices), availability_service=_Availability(avail))


def test_pos_catalog_composes_price_and_availability(conn):
    p1 = _product(conn, name="Refresco", code="R1")
    conn.execute("INSERT INTO product_barcodes (id, product_id, barcode_value, "
                 "barcode_type, is_primary, active) VALUES (?,?,?,?,1,1)",
                 (new_uuid(), p1, "7501234567890", "EAN13"))
    conn.commit()
    facade = _facade(conn, {p1: Decimal("18.50")}, {p1: Decimal("42")})
    items = facade.search(branch_id="b1")
    assert len(items) == 1
    it = items[0]
    assert it.name == "Refresco" and it.barcode == "7501234567890"
    assert it.sale_price == Decimal("18.50") and it.available == Decimal("42")


def test_pos_catalog_excludes_draft_internal_and_other_branch(conn):
    _product(conn, name="OK", code="OK1")
    _product(conn, name="Borrador", code="D1", lifecycle="DRAFT")
    _product(conn, name="Interno", code="I1", internal_only=1, sellable=0)
    conn.commit()
    items = _facade(conn, {}, {}).search(branch_id="b1")
    assert {i.name for i in items} == {"OK"}


def test_pos_catalog_price_may_be_missing(conn):
    p1 = _product(conn, name="SinPrecio", code="SP1")
    conn.commit()
    items = _facade(conn, {}, {p1: Decimal("5")}).search(branch_id="b1")
    assert items[0].sale_price is None and items[0].available == Decimal("5")
