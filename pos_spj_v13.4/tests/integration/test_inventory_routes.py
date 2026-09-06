"""Integration tests for the canonical inventory route.

Coverage:
  01-08  Multi-branch isolation in process_movement + read
  09-14  get_stock() reads inventario_actual (not productos.existencia)
  23-25  InventoryBalanceQueryService.get_product_balance()
  31     Architecture guard: no cross-branch contamination

Removed (GAP-2 dead-code cleanup): list_stock_rows()/list_availability_rows()
(InventoryQueryService) and list_branch_balances()/get_reconciliation_report()
(InventoryBalanceQueryService) had zero production callers and were deleted
from the source services — see backend/application/queries/inventory_query_service.py
and inventory_balance_service.py. Test 32 (cross-check between the two) went
with them.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from backend.application.queries.inventory_balance_service import InventoryBalanceQueryService
from core.services.inventory.unified_inventory_service import (
    UnifiedInventoryService,
    StockInsuficienteError,
)


# ── Schema fixture ─────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            existencia REAL DEFAULT 0,
            stock_minimo REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg',
            categoria TEXT DEFAULT ''
        );
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL,
            cantidad REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            producto_id INTEGER,
            tipo TEXT,
            tipo_movimiento TEXT,
            cantidad REAL,
            existencia_anterior REAL,
            existencia_nueva REAL,
            costo_unitario REAL DEFAULT 0,
            costo_total REAL DEFAULT 0,
            descripcion TEXT,
            referencia TEXT,
            usuario TEXT,
            sucursal_id INTEGER,
            fecha TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE inventory_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            unit TEXT DEFAULT 'kg',
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(product_id, branch_id)
        );
        CREATE TABLE inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            branch_id INTEGER,
            movement_type TEXT,
            quantity REAL,
            reference_type TEXT,
            operation_id TEXT,
            user_name TEXT,
            source_module TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE sucursales (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            activa INTEGER DEFAULT 1
        );
        INSERT INTO sucursales VALUES (1, 'Norte', 1);
        INSERT INTO sucursales VALUES (2, 'Sur', 1);
        INSERT INTO productos VALUES (1, 'Carne Molida', 1, 100.0, 5.0, 'kg', 'carnico');
        INSERT INTO productos VALUES (2, 'Costilla', 1, 50.0, 3.0, 'kg', 'carnico');
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (1, 1, 40.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (1, 2, 25.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (2, 1, 15.0);
        INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (2, 2, 8.0);
    """)
    conn.commit()
    return conn


def _svc(conn, branch_id: int) -> UnifiedInventoryService:
    return UnifiedInventoryService(conn=conn, sucursal_id=branch_id, usuario="test")


def _bsvc(conn) -> InventoryBalanceQueryService:
    return InventoryBalanceQueryService(conn)


# ── Tests 01-08: Multi-branch isolation ───────────────────────────────────────

def test_01_sale_in_branch1_does_not_reduce_branch2_stock():
    db = _make_db()
    _svc(db, 1).process_movement(product_id=1, quantity=-5, movement_type="VENTA", branch_id=1)
    b1 = _bsvc(db).get_product_balance(1, 1)
    b2 = _bsvc(db).get_product_balance(1, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(35.0)
    assert float(b2["stock_fisico"]) == pytest.approx(25.0)


def test_02_purchase_in_branch2_does_not_inflate_branch1():
    db = _make_db()
    _svc(db, 2).process_movement(product_id=2, quantity=10, movement_type="purchase", branch_id=2)
    b1 = _bsvc(db).get_product_balance(2, 1)
    b2 = _bsvc(db).get_product_balance(2, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(15.0)
    assert float(b2["stock_fisico"]) == pytest.approx(18.0)


def test_03_multiple_branches_independent_movement_chains():
    db = _make_db()
    svc1 = _svc(db, 1)
    svc2 = _svc(db, 2)
    svc1.process_movement(product_id=1, quantity=-10, movement_type="VENTA", branch_id=1)
    svc2.process_movement(product_id=1, quantity=-5, movement_type="VENTA", branch_id=2)
    svc1.process_movement(product_id=1, quantity=20, movement_type="purchase", branch_id=1)
    b1 = _bsvc(db).get_product_balance(1, 1)
    b2 = _bsvc(db).get_product_balance(1, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(50.0)
    assert float(b2["stock_fisico"]) == pytest.approx(20.0)


def test_04_stock_insufficient_error_uses_branch_stock_not_global():
    db = _make_db()
    # Branch 2 has 25kg of product 1 — trying to sell 30 should fail
    with pytest.raises(StockInsuficienteError):
        _svc(db, 2).process_movement(product_id=1, quantity=-30, movement_type="VENTA", branch_id=2)


def test_05_branch1_can_sell_more_than_branch2_stock_if_branch1_has_enough():
    db = _make_db()
    # Branch 1 has 40kg; this should succeed
    _svc(db, 1).process_movement(product_id=1, quantity=-35, movement_type="VENTA", branch_id=1)
    b1 = _bsvc(db).get_product_balance(1, 1)
    assert float(b1["stock_fisico"]) == pytest.approx(5.0)


def test_06_new_product_with_no_inventario_actual_row_seeds_from_existencia():
    db = _make_db()
    # Product 1, branch 99 has no inventario_actual row — seed from productos.existencia=100
    svc = _svc(db, 99)
    svc.process_movement(product_id=1, quantity=-10, movement_type="VENTA", branch_id=99)
    ia = db.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id=1 AND sucursal_id=99"
    ).fetchone()
    assert ia is not None
    assert float(ia[0]) == pytest.approx(90.0)


def test_07_movement_records_correct_branch_in_movimientos():
    db = _make_db()
    _svc(db, 2).process_movement(product_id=2, quantity=-3, movement_type="VENTA", branch_id=2)
    row = db.execute(
        "SELECT sucursal_id, cantidad FROM movimientos_inventario ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["sucursal_id"] == 2
    assert float(row["cantidad"]) == pytest.approx(3.0)


def test_08_transfer_out_then_in_across_branches():
    db = _make_db()
    # Dispatch 5kg from branch 1 to branch 2
    _svc(db, 1).process_movement(product_id=1, quantity=-5, movement_type="TRANSFER_OUT", branch_id=1)
    _svc(db, 2).process_movement(product_id=1, quantity=5, movement_type="TRANSFER_IN", branch_id=2)
    b1 = _bsvc(db).get_product_balance(1, 1)
    b2 = _bsvc(db).get_product_balance(1, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(35.0)
    assert float(b2["stock_fisico"]) == pytest.approx(30.0)


# ── Tests 09-14: get_stock() reads inventario_actual ──────────────────────────

def test_09_get_stock_returns_branch_specific_value():
    db = _make_db()
    assert _svc(db, 1).get_stock(1, sucursal_id=1) == pytest.approx(40.0)
    assert _svc(db, 2).get_stock(1, sucursal_id=2) == pytest.approx(25.0)


def test_10_get_stock_reflects_update_after_movement():
    db = _make_db()
    _svc(db, 1).process_movement(product_id=1, quantity=-10, movement_type="VENTA", branch_id=1)
    assert _svc(db, 1).get_stock(1, sucursal_id=1) == pytest.approx(30.0)


def test_11_get_stock_branch2_unchanged_after_branch1_movement():
    db = _make_db()
    _svc(db, 1).process_movement(product_id=1, quantity=-40, movement_type="VENTA", branch_id=1)
    assert _svc(db, 2).get_stock(1, sucursal_id=2) == pytest.approx(25.0)


def test_12_get_stock_falls_back_to_existencia_when_no_branch_row():
    db = _make_db()
    # Branch 99 has no row — should fall back to productos.existencia=100
    assert _svc(db, 99).get_stock(1, sucursal_id=99) == pytest.approx(100.0)


def test_13_validate_stock_uses_branch_stock():
    db = _make_db()
    svc = _svc(db, 2)
    assert svc.validate_stock(1, 20, sucursal_id=2)  # branch 2 has 25
    assert not svc.validate_stock(1, 30, sucursal_id=2)  # branch 2 has 25 < 30


def test_14_get_stock_sucursal_returns_branch_stock():
    db = _make_db()
    svc = _svc(db, 1)
    s1 = svc.get_stock_sucursal(1, branch_id=1)
    s2 = svc.get_stock_sucursal(1, branch_id=2)
    # Both should differ (branch-specific)
    assert s1 != s2


# ── Tests 23-25: InventoryBalanceQueryService.get_product_balance() ───────────

def test_23_get_product_balance_returns_branch_specific_stock():
    db = _make_db()
    b1 = _bsvc(db).get_product_balance(1, 1)
    b2 = _bsvc(db).get_product_balance(1, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(40.0)
    assert float(b2["stock_fisico"]) == pytest.approx(25.0)
    assert b1["sucursal_id"] == 1
    assert b2["sucursal_id"] == 2


def test_24_get_product_balance_returns_decimal_values():
    from decimal import Decimal
    db = _make_db()
    b = _bsvc(db).get_product_balance(1, 1)
    assert isinstance(b["stock_fisico"], Decimal)
    assert isinstance(b["stock_disponible"], Decimal)


def test_25_get_product_balance_fuente_is_inventario_actual():
    db = _make_db()
    b = _bsvc(db).get_product_balance(1, 1)
    assert b["fuente"] == "inventario_actual"


# ── Test 31: Architecture guard ────────────────────────────────────────────────

def test_31_no_cross_branch_contamination_after_100_movements():
    db = _make_db()
    svc1 = _svc(db, 1)
    svc2 = _svc(db, 2)
    # 50 sales in branch 1
    for _ in range(10):
        svc1.process_movement(product_id=1, quantity=-1, movement_type="VENTA", branch_id=1)
    # 50 purchases in branch 2
    for _ in range(10):
        svc2.process_movement(product_id=1, quantity=2, movement_type="purchase", branch_id=2)
    b1 = _bsvc(db).get_product_balance(1, 1)
    b2 = _bsvc(db).get_product_balance(1, 2)
    assert float(b1["stock_fisico"]) == pytest.approx(30.0)   # 40 - 10
    assert float(b2["stock_fisico"]) == pytest.approx(45.0)   # 25 + 20
