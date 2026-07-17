"""PUR-13 step 2d — PurchaseLotEntryHandler creates meat/poultry lots on receipt.

Replicates the monolith's _crear_lotes_compra / LoteService.registrar_lote at the
Inventory context: a lot per weight-tracked line, per-lot cost, a 'recepcion'
movement, idempotent. Non-weight lines create no lot.
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.event_handlers.inventory.purchase_lot_entry_handler import (
    PurchaseLotEntryHandler,
)


@pytest.fixture
def inv_conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE lotes (id TEXT PRIMARY KEY, producto_id TEXT, numero_lote TEXT,"
        " proveedor_id TEXT, fecha_recepcion DATE DEFAULT (date('now')), fecha_caducidad DATE,"
        " peso_inicial_kg REAL DEFAULT 0, peso_actual_kg REAL DEFAULT 0, costo_kg REAL DEFAULT 0,"
        " sucursal_id TEXT, estado TEXT DEFAULT 'activo', temperatura_c REAL, observaciones TEXT,"
        " tipo_origen TEXT DEFAULT 'compra', UNIQUE(numero_lote, producto_id))")
    c.execute(
        "CREATE TABLE movimientos_lote (id TEXT PRIMARY KEY, lote_id TEXT, tipo TEXT,"
        " cantidad_kg REAL, referencia TEXT, usuario TEXT, fecha DATETIME DEFAULT (datetime('now')))")
    yield c
    c.close()


def _event(lines, event_id="e1", document="CD-2026-000001"):
    return {"event_id": event_id, "document_number": document, "warehouse_id": "wh-1",
            "supplier_id": "prov1", "user_id": "alm", "lines": lines}


def test_weight_line_creates_lot(inv_conn):
    PurchaseLotEntryHandler(inv_conn).handle(_event(
        [{"product_id": "p1", "quantity": "12.5", "unit_cost": "40", "inventory_unit": "KG"}]))
    lot = inv_conn.execute(
        "SELECT numero_lote, peso_inicial_kg, peso_actual_kg, costo_kg, proveedor_id, estado,"
        " tipo_origen FROM lotes WHERE producto_id='p1'").fetchone()
    assert lot[0] == "CD-2026-000001-Pp1"  # numero_lote = {document}-P{product_id}
    assert Decimal(str(lot[1])) == Decimal("12.5") and Decimal(str(lot[2])) == Decimal("12.5")
    assert Decimal(str(lot[3])) == Decimal("40") and lot[4] == "prov1"
    assert lot[5] == "activo" and lot[6] == "compra"
    mov = inv_conn.execute(
        "SELECT tipo, cantidad_kg, referencia FROM movimientos_lote").fetchone()
    assert mov[0] == "recepcion" and Decimal(str(mov[1])) == Decimal("12.5")
    assert mov[2] == "CD-2026-000001"


def test_non_weight_line_creates_no_lot(inv_conn):
    PurchaseLotEntryHandler(inv_conn).handle(_event(
        [{"product_id": "p2", "quantity": "5", "unit_cost": "8", "inventory_unit": "PZA"}]))
    assert inv_conn.execute("SELECT COUNT(*) FROM lotes").fetchone()[0] == 0


def test_expiration_marks_lot_even_if_not_weight(inv_conn):
    PurchaseLotEntryHandler(inv_conn).handle(_event(
        [{"product_id": "p3", "quantity": "3", "unit_cost": "10", "inventory_unit": "PZA",
          "expiration": "2026-12-31"}]))
    lot = inv_conn.execute(
        "SELECT fecha_caducidad FROM lotes WHERE producto_id='p3'").fetchone()
    assert lot and lot[0] == "2026-12-31"


def test_idempotent_by_lot_number(inv_conn):
    ev = _event([{"product_id": "p1", "quantity": "10", "unit_cost": "40",
                  "inventory_unit": "KG"}], event_id="dup")
    PurchaseLotEntryHandler(inv_conn).handle(ev)
    PurchaseLotEntryHandler(inv_conn).handle(ev)  # replay
    assert inv_conn.execute("SELECT COUNT(*) FROM lotes").fetchone()[0] == 1
    assert inv_conn.execute("SELECT COUNT(*) FROM movimientos_lote").fetchone()[0] == 1


def test_mixed_lines_only_weight_gets_lot(inv_conn):
    PurchaseLotEntryHandler(inv_conn).handle(_event([
        {"product_id": "pollo", "quantity": "20", "unit_cost": "55", "inventory_unit": "KG"},
        {"product_id": "caja", "quantity": "10", "unit_cost": "8", "inventory_unit": "PZA"}]))
    lots = [r[0] for r in inv_conn.execute("SELECT producto_id FROM lotes").fetchall()]
    assert lots == ["pollo"]
