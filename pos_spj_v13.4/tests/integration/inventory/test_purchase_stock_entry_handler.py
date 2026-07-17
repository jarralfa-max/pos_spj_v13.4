"""PUR-13 step 2a — PurchaseStockEntryHandler applies purchase receipts to stock.

Replicates the legacy weighted-average costing + stock sync at the Inventory
context (its correct owner), idempotently. Uses the real
trg_recalc_inventario_actual trigger so cantidad is updated exactly as in prod.
"""

from decimal import Decimal

import pytest

from backend.application.event_handlers.inventory.purchase_stock_entry_handler import (
    PurchaseStockEntryHandler,
)


@pytest.fixture
def inv_conn():
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id TEXT,"
        " sucursal_id TEXT, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0,"
        " ultima_actualizacion TEXT, UNIQUE(producto_id, sucursal_id))")
    c.execute(
        "CREATE TABLE movimientos_inventario (id TEXT PRIMARY KEY, producto_id TEXT,"
        " tipo TEXT, tipo_movimiento TEXT, cantidad REAL, costo_unitario REAL,"
        " descripcion TEXT, referencia TEXT, referencia_id TEXT, referencia_tipo TEXT,"
        " proveedor_id TEXT, usuario TEXT, sucursal_id TEXT)")
    c.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, existencia REAL DEFAULT 0,"
              " precio_compra REAL DEFAULT 0)")
    c.execute("""
        CREATE TRIGGER trg_recalc_inventario_actual
        AFTER INSERT ON movimientos_inventario
        WHEN NEW.producto_id IS NOT NULL AND NEW.sucursal_id IS NOT NULL
        BEGIN
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, ultima_actualizacion)
            VALUES (NEW.producto_id, NEW.sucursal_id,
                CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END,
                datetime('now'))
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad = inventario_actual.cantidad +
                    CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END,
                ultima_actualizacion = datetime('now');
        END""")
    c.execute("INSERT INTO productos (id, existencia, precio_compra) VALUES ('p1',0,0)")
    yield c
    c.close()


def _event(event_id="e1", lines=None):
    return {"event_id": event_id, "operation_id": "op", "warehouse_id": "wh-1",
            "branch_id": "br-1", "supplier_id": "s1", "user_id": "alm",
            "goods_receipt_id": "gr-1",
            "lines": lines or [{"product_id": "p1", "quantity": "10", "unit_cost": "30"}]}


def test_stock_entry_increases_quantity_and_syncs_existencia(inv_conn):
    PurchaseStockEntryHandler(inv_conn).handle(_event())
    row = inv_conn.execute(
        "SELECT cantidad, costo_promedio FROM inventario_actual"
        " WHERE producto_id='p1' AND sucursal_id='wh-1'").fetchone()
    assert Decimal(str(row[0])) == Decimal("10")
    assert Decimal(str(row[1])) == Decimal("30")
    prod = inv_conn.execute("SELECT existencia, precio_compra FROM productos"
                           " WHERE id='p1'").fetchone()
    assert Decimal(str(prod[0])) == Decimal("10") and Decimal(str(prod[1])) == Decimal("30")


def test_weighted_average_cost(inv_conn):
    PurchaseStockEntryHandler(inv_conn).handle(
        _event("e1", [{"product_id": "p1", "quantity": "10", "unit_cost": "30"}]))
    PurchaseStockEntryHandler(inv_conn).handle(
        _event("e2", [{"product_id": "p1", "quantity": "10", "unit_cost": "50"}]))
    row = inv_conn.execute(
        "SELECT cantidad, costo_promedio FROM inventario_actual"
        " WHERE producto_id='p1' AND sucursal_id='wh-1'").fetchone()
    # (10*30 + 10*50) / 20 = 40
    assert Decimal(str(row[0])) == Decimal("20")
    assert Decimal(str(row[1])) == Decimal("40")


def test_idempotent_by_event_id(inv_conn):
    ev = _event("dup")
    PurchaseStockEntryHandler(inv_conn).handle(ev)
    PurchaseStockEntryHandler(inv_conn).handle(ev)   # replay
    qty = inv_conn.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id='p1'").fetchone()[0]
    moves = inv_conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0]
    assert Decimal(str(qty)) == Decimal("10") and moves == 1


def test_multiple_lines_apply_atomically(inv_conn):
    inv_conn.execute("INSERT INTO productos (id) VALUES ('p2')")
    PurchaseStockEntryHandler(inv_conn).handle(_event("multi", [
        {"product_id": "p1", "quantity": "4", "unit_cost": "10"},
        {"product_id": "p2", "quantity": "6", "unit_cost": "20"}]))
    q1 = inv_conn.execute("SELECT cantidad FROM inventario_actual"
                         " WHERE producto_id='p1'").fetchone()[0]
    q2 = inv_conn.execute("SELECT cantidad FROM inventario_actual"
                         " WHERE producto_id='p2'").fetchone()[0]
    assert Decimal(str(q1)) == Decimal("4") and Decimal(str(q2)) == Decimal("6")


def test_no_warehouse_or_lines_is_noop(inv_conn):
    PurchaseStockEntryHandler(inv_conn).handle({"event_id": "x", "lines": []})
    assert inv_conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0] == 0
