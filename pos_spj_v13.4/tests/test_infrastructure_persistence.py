# tests/test_infrastructure_persistence.py — SPJ ERP v13.4
"""
Tests for infrastructure/persistence/ repositories.

Verifies that SQLiteSalesRepository and SQLiteInventoryRepository correctly
read/write to SQLite without any business logic leaking in.
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# DB fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT UNIQUE,
            sucursal_id INTEGER, usuario TEXT, cliente_id INTEGER,
            subtotal REAL DEFAULT 0, descuento REAL DEFAULT 0, total REAL DEFAULT 0,
            forma_pago TEXT DEFAULT 'Efectivo', efectivo_recibido REAL DEFAULT 0,
            operation_id TEXT, observations TEXT,
            estado TEXT DEFAULT 'completada',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER, producto_id INTEGER,
            cantidad REAL, precio_unitario REAL, subtotal REAL,
            costo_unitario_real REAL DEFAULT 0, descuento REAL DEFAULT 0
        );
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY, nombre TEXT, apellido TEXT
        );
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            existencia REAL DEFAULT 0, stock_minimo REAL DEFAULT 5, unidad TEXT DEFAULT 'pza'
        );
        CREATE TABLE inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL, sucursal_id INTEGER DEFAULT 1,
            cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0,
            ultima_actualizacion DATETIME DEFAULT (datetime('now')),
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER, branch_id INTEGER,
            quantity REAL, movement_type TEXT,
            operation_id TEXT, usuario TEXT,
            reference_type TEXT DEFAULT '', reference_id TEXT DEFAULT '',
            notes TEXT DEFAULT '', created_at DATETIME DEFAULT (datetime('now'))
        );
        INSERT INTO productos VALUES (1,'Pollo',50.0,5.0,'kg');
        INSERT INTO productos VALUES (2,'Pechuga',30.0,3.0,'kg');
        INSERT INTO clientes VALUES (1,'Juan','Perez');
        INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad, costo_promedio)
            VALUES (1,1,100.0,45.0),(2,1,50.0,60.0);
    """)
    return conn


@pytest.fixture
def sales_repo(db):
    from infrastructure.persistence.sqlite_sales_repository import SQLiteSalesRepository
    return SQLiteSalesRepository(db)


@pytest.fixture
def inv_repo(db):
    from infrastructure.persistence.sqlite_inventory_repository import SQLiteInventoryRepository
    return SQLiteInventoryRepository(db)


# ─────────────────────────────────────────────────────────────────────────────
# SQLiteSalesRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteSalesRepository:
    def test_create_sale_returns_id_and_folio(self, sales_repo):
        sid, folio = sales_repo.create_sale(
            branch_id=1, user="cajero", client_id=1,
            subtotal=100.0, discount=0.0, total=100.0,
            payment_method="Efectivo", amount_paid=100.0,
            operation_id="op-001",
        )
        assert sid > 0
        assert folio.startswith("VNT-")

    def test_create_sale_folio_is_unique_per_call(self, sales_repo):
        _, folio1 = sales_repo.create_sale(
            branch_id=1, user="cajero", client_id=None,
            subtotal=50.0, discount=0.0, total=50.0,
            payment_method="Efectivo", amount_paid=50.0,
            operation_id="op-002",
        )
        _, folio2 = sales_repo.create_sale(
            branch_id=1, user="cajero", client_id=None,
            subtotal=80.0, discount=0.0, total=80.0,
            payment_method="Efectivo", amount_paid=80.0,
            operation_id="op-003",
        )
        assert folio1 != folio2

    def test_save_sale_item_inserts_row(self, sales_repo, db):
        sid, _ = sales_repo.create_sale(
            branch_id=1, user="x", client_id=None,
            subtotal=150.0, discount=0.0, total=150.0,
            payment_method="Efectivo", amount_paid=150.0,
            operation_id="op-100",
        )
        sales_repo.save_sale_item(sale_id=sid, product_id=1, qty=2.0, unit_price=75.0, subtotal=150.0)
        count = db.execute("SELECT COUNT(*) FROM detalles_venta WHERE venta_id=?", (sid,)).fetchone()[0]
        assert count == 1

    def test_get_by_id_returns_dict(self, sales_repo):
        sid, _ = sales_repo.create_sale(
            branch_id=1, user="x", client_id=1,
            subtotal=200.0, discount=10.0, total=190.0,
            payment_method="Tarjeta", amount_paid=190.0,
            operation_id="op-200",
        )
        row = sales_repo.get_by_id(sid)
        assert row is not None
        assert row["total"] == pytest.approx(190.0)
        assert row["forma_pago"] == "Tarjeta"

    def test_get_by_id_nonexistent_returns_none(self, sales_repo):
        assert sales_repo.get_by_id(99999) is None

    def test_get_by_folio(self, sales_repo):
        sid, folio = sales_repo.create_sale(
            branch_id=1, user="y", client_id=None,
            subtotal=300.0, discount=0.0, total=300.0,
            payment_method="Efectivo", amount_paid=300.0,
            operation_id="op-300",
        )
        row = sales_repo.get_by_folio(folio)
        assert row is not None
        assert row["id"] == sid

    def test_get_by_operation_id(self, sales_repo):
        sales_repo.create_sale(
            branch_id=1, user="z", client_id=None,
            subtotal=400.0, discount=0.0, total=400.0,
            payment_method="Efectivo", amount_paid=400.0,
            operation_id="unique-op-xyz",
        )
        row = sales_repo.get_by_operation_id("unique-op-xyz")
        assert row is not None
        assert row["total"] == pytest.approx(400.0)

    def test_get_by_operation_id_missing_returns_none(self, sales_repo):
        assert sales_repo.get_by_operation_id("does-not-exist") is None

    def test_cancel_sale_marks_cancelled(self, sales_repo, db):
        sid, _ = sales_repo.create_sale(
            branch_id=1, user="mgr", client_id=None,
            subtotal=100.0, discount=0.0, total=100.0,
            payment_method="Efectivo", amount_paid=100.0,
            operation_id="op-cancel",
        )
        sales_repo.cancel_sale(sid, reason="Error de cliente")
        row = db.execute("SELECT estado FROM ventas WHERE id=?", (sid,)).fetchone()
        assert row["estado"] == "cancelada"

    def test_get_items_returns_all_items(self, sales_repo):
        sid, _ = sales_repo.create_sale(
            branch_id=1, user="x", client_id=None,
            subtotal=175.0, discount=0.0, total=175.0,
            payment_method="Efectivo", amount_paid=175.0,
            operation_id="op-items",
        )
        sales_repo.save_sale_item(sid, 1, 2.0, 50.0, 100.0)
        sales_repo.save_sale_item(sid, 2, 1.0, 75.0, 75.0)
        items = sales_repo.get_items(sid)
        assert len(items) == 2

    def test_get_today_returns_todays_sales(self, sales_repo):
        sales_repo.create_sale(
            branch_id=1, user="cajero", client_id=None,
            subtotal=500.0, discount=0.0, total=500.0,
            payment_method="Efectivo", amount_paid=500.0,
            operation_id="op-today",
        )
        rows = sales_repo.get_today(branch_id=1)
        assert len(rows) >= 1
        assert all(r["estado"] != "cancelada" for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# SQLiteInventoryRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteInventoryRepository:
    def test_get_stock_returns_quantity(self, inv_repo):
        assert inv_repo.get_stock(1, 1) == pytest.approx(100.0)

    def test_get_stock_falls_back_to_productos_existencia(self, inv_repo, db):
        db.execute("DELETE FROM inventario_actual WHERE producto_id=2")
        assert inv_repo.get_stock(2, 1) == pytest.approx(30.0)

    def test_get_stock_missing_returns_zero(self, inv_repo):
        assert inv_repo.get_stock(999, 1) == pytest.approx(0.0)

    def test_add_stock_increments(self, inv_repo):
        inv_repo.add_stock(product_id=1, branch_id=1, quantity=20.0)
        assert inv_repo.get_stock(1, 1) == pytest.approx(120.0)

    def test_deduct_stock_decrements(self, inv_repo):
        inv_repo.deduct_stock(product_id=1, branch_id=1, quantity=15.0)
        assert inv_repo.get_stock(1, 1) == pytest.approx(85.0)

    def test_upsert_stock_sets_absolute_value(self, inv_repo):
        inv_repo.upsert_stock(product_id=1, branch_id=1, quantity=999.0)
        assert inv_repo.get_stock(1, 1) == pytest.approx(999.0)

    def test_log_movement_inserts_row(self, inv_repo, db):
        inv_repo.log_movement(
            product_id=1, branch_id=1, quantity=-5.0,
            movement_type="VENTA", operation_id="op-mv-001", user="cajero",
        )
        count = db.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0]
        assert count == 1

    def test_get_movements_returns_records(self, inv_repo):
        inv_repo.log_movement(1, 1, -3.0, "VENTA", "mv-1", "x")
        inv_repo.log_movement(1, 1,  5.0, "ENTRADA", "mv-2", "y")
        mvs = inv_repo.get_movements(product_id=1, branch_id=1)
        assert len(mvs) == 2

    def test_get_all_stock_returns_products(self, inv_repo):
        rows = inv_repo.get_all_stock(branch_id=1)
        assert len(rows) >= 2
        names = [r["nombre"] for r in rows]
        assert "Pollo" in names

    def test_get_low_stock_filters_correctly(self, inv_repo, db):
        db.execute("UPDATE inventario_actual SET cantidad=2.0 WHERE producto_id=1")
        low = inv_repo.get_low_stock(branch_id=1)
        ids = [r["producto_id"] for r in low]
        assert 1 in ids  # stock 2 < minimo 5

    def test_add_stock_new_product_creates_row(self, inv_repo):
        inv_repo.add_stock(product_id=99, branch_id=1, quantity=10.0)
        assert inv_repo.get_stock(99, 1) == pytest.approx(10.0)
