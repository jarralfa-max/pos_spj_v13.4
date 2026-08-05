"""INV-27 corte (compras) — la recepción de compra (PURCHASE_STOCK_ENTRY_REGISTERED)
postea un PURCHASE_RECEIPT canónico al ledger, no a movimientos_inventario legacy.

Corrige la divergencia: tras el corte todos los escritores son canónicos; si las
compras siguieran escribiendo tablas legacy, el stock comprado nunca aparecería en
la proyección que lee el POS.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory.purchase_stock_entry_bridge import (
    CanonicalPurchaseStockEntryHandler,
)
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _available(conn, product_id="p1", branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _payload(event_id="gr-1", qty="10"):
    return {"event_id": event_id, "warehouse_id": "b1", "user_id": "u1",
            "goods_receipt_id": "GR-1", "supplier_id": "s1",
            "lines": [{"product_id": "p1", "quantity": qty, "unit_cost": "5"}]}


def test_receipt_posts_canonical_purchase_receipt(conn):
    CanonicalPurchaseStockEntryHandler(conn).handle(_payload(qty="10"))
    assert _available(conn) == Decimal("10")
    row = conn.execute("SELECT movement_type FROM inventory_ledger"
                       " WHERE operation_id='gr-1'").fetchone()
    assert row["movement_type"] == "PURCHASE_RECEIPT"


def test_receipt_is_idempotent(conn):
    CanonicalPurchaseStockEntryHandler(conn).handle(_payload(event_id="gr-1", qty="10"))
    CanonicalPurchaseStockEntryHandler(conn).handle(_payload(event_id="gr-1", qty="10"))
    assert _available(conn) == Decimal("10")  # once


def test_receipt_carries_unit_cost_on_line(conn):
    CanonicalPurchaseStockEntryHandler(conn).handle(_payload(qty="4"))
    row = conn.execute("SELECT unit_cost FROM inventory_ledger_lines"
                       " WHERE product_id='p1'").fetchone()
    assert Decimal(str(row["unit_cost"])) == Decimal("5")


def test_lot_coded_receipt_creates_canonical_lot(conn):
    payload = _payload(qty="6")
    payload["lines"][0]["lot_code"] = "LOTE-A"
    CanonicalPurchaseStockEntryHandler(conn).handle(payload)
    assert _available(conn) == Decimal("6")
    lot = conn.execute("SELECT lot_code FROM inventory_lots WHERE lot_code='LOTE-A'").fetchone()
    assert lot is not None


# ── P2 slice 2: canonical lots for lot-tracked live lines (legacy parity) ──────
def test_weight_tracked_line_creates_deterministic_canonical_lot(conn):
    # línea de peso (KG) sin lot_code explícito → lote canónico {document}-P{pid}
    payload = _payload(qty="7")
    payload["lines"][0]["inventory_unit"] = "KG"
    CanonicalPurchaseStockEntryHandler(conn).handle(payload)
    lot = conn.execute(
        "SELECT lot_code FROM inventory_lots WHERE product_id='p1'").fetchone()
    assert lot is not None and lot["lot_code"] == "GR-1-Pp1"


def test_explicit_lot_field_maps_to_canonical_lot_code(conn):
    payload = _payload(qty="3")
    payload["lines"][0]["lot"] = "L-EXP"
    CanonicalPurchaseStockEntryHandler(conn).handle(payload)
    lot = conn.execute(
        "SELECT lot_code FROM inventory_lots WHERE product_id='p1'").fetchone()
    assert lot is not None and lot["lot_code"] == "L-EXP"


def test_non_tracked_line_creates_no_lot(conn):
    # sin unidad de peso, sin expiration, sin lot → no se crea lote
    CanonicalPurchaseStockEntryHandler(conn).handle(_payload(qty="5"))
    assert conn.execute("SELECT COUNT(*) c FROM inventory_lots").fetchone()["c"] == 0


def test_weight_tracked_lot_creation_is_idempotent(conn):
    payload = _payload(event_id="gr-1", qty="7")
    payload["lines"][0]["inventory_unit"] = "KG"
    CanonicalPurchaseStockEntryHandler(conn).handle(payload)
    CanonicalPurchaseStockEntryHandler(conn).handle(payload)  # replay
    assert conn.execute("SELECT COUNT(*) c FROM inventory_lots"
                        " WHERE product_id='p1'").fetchone()["c"] == 1
