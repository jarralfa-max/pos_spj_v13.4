# tests/test_infrastructure_persistence.py — SPJ ERP v13.4
"""Tests for infrastructure/persistence/ repositories (UUID-only schema)."""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.shared.ids import new_uuid

# ── Fixed UUIDs for reproducible tests ────────────────────────────────────────

BRANCH_UUID   = "01900000-0000-7000-8000-000000000011"
PRODUCT_UUID  = "01900000-0000-7000-8000-000000000001"
PRODUCT2_UUID = "01900000-0000-7000-8000-000000000002"
CLIENT_UUID   = "01900000-0000-7000-8000-000000000021"


# ─────────────────────────────────────────────────────────────────────────────
# DB fixtures (UUID-only canonical schema)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(f"""
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY,
            folio TEXT UNIQUE,
            sucursal_id TEXT, usuario TEXT, cliente_id TEXT,
            subtotal REAL DEFAULT 0, descuento REAL DEFAULT 0, total REAL DEFAULT 0,
            forma_pago TEXT DEFAULT 'Efectivo', efectivo_recibido REAL DEFAULT 0,
            operation_id TEXT, observations TEXT,
            estado TEXT DEFAULT 'completada',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY,
            venta_id TEXT, producto_id TEXT,
            cantidad REAL, precio_unitario REAL, subtotal REAL,
            costo_unitario_real REAL DEFAULT 0, descuento REAL DEFAULT 0
        );
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT
        );
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, nombre TEXT,
            existencia REAL DEFAULT 0, stock_minimo REAL DEFAULT 5,
            unidad TEXT DEFAULT 'pza'
        );
        CREATE TABLE inventory_stock (
            product_id TEXT NOT NULL,
            branch_id  TEXT NOT NULL,
            quantity   REAL NOT NULL DEFAULT 0,
            unit       TEXT NOT NULL DEFAULT 'kg',
            updated_at DATETIME DEFAULT (datetime('now')),
            PRIMARY KEY (product_id, branch_id)
        );
        CREATE TABLE inventory_movements (
            id            TEXT PRIMARY KEY,
            product_id    TEXT NOT NULL,
            branch_id     TEXT NOT NULL,
            quantity      REAL NOT NULL,
            movement_type TEXT NOT NULL,
            operation_id  TEXT,
            user_name     TEXT,
            reference_type TEXT DEFAULT '',
            reference_id   TEXT DEFAULT '',
            notes          TEXT DEFAULT '',
            created_at     DATETIME DEFAULT (datetime('now'))
        );
        INSERT INTO productos VALUES ('{PRODUCT_UUID}',  'Pollo',   50.0, 5.0, 'kg');
        INSERT INTO productos VALUES ('{PRODUCT2_UUID}', 'Pechuga', 30.0, 3.0, 'kg');
        INSERT INTO clientes VALUES ('{CLIENT_UUID}', 'Juan Perez');
        INSERT INTO inventory_stock VALUES ('{PRODUCT_UUID}',  '{BRANCH_UUID}', 100.0, 'kg', datetime('now'));
        INSERT INTO inventory_stock VALUES ('{PRODUCT2_UUID}', '{BRANCH_UUID}',  50.0, 'kg', datetime('now'));
    """)
    return conn


@pytest.fixture
def sales_repo(db):
    from infrastructure.persistence.sqlite_sales_repository import SQLiteSalesRepository
    return SQLiteSalesRepository(db)


# ─────────────────────────────────────────────────────────────────────────────
# SQLiteSalesRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLiteSalesRepository:
    def test_create_sale_returns_uuid_and_folio(self, sales_repo):
        sid, folio = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="cajero", client_id=CLIENT_UUID,
            subtotal=100.0, discount=0.0, total=100.0,
            payment_method="Efectivo", amount_paid=100.0,
            operation_id=new_uuid(),
        )
        assert "-" in sid, "sale_id debe ser UUID"
        assert not sid.isdigit(), "sale_id no debe ser entero"
        assert folio.startswith("VNT-")

    def test_sale_id_is_uuid_not_integer(self, sales_repo):
        sid, _ = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="cajero", client_id=None,
            subtotal=50.0, discount=0.0, total=50.0,
            payment_method="Efectivo", amount_paid=50.0,
            operation_id=new_uuid(),
        )
        assert not sid.isdigit()
        assert len(sid) >= 32

    def test_create_sale_folio_is_unique_per_call(self, sales_repo):
        _, folio1 = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="cajero", client_id=None,
            subtotal=50.0, discount=0.0, total=50.0,
            payment_method="Efectivo", amount_paid=50.0,
            operation_id=new_uuid(),
        )
        _, folio2 = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="cajero", client_id=None,
            subtotal=80.0, discount=0.0, total=80.0,
            payment_method="Efectivo", amount_paid=80.0,
            operation_id=new_uuid(),
        )
        assert folio1 != folio2

    def test_save_sale_item_inserts_row(self, sales_repo, db):
        sid, _ = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="x", client_id=None,
            subtotal=150.0, discount=0.0, total=150.0,
            payment_method="Efectivo", amount_paid=150.0,
            operation_id=new_uuid(),
        )
        sales_repo.save_sale_item(
            sale_id=sid, product_id=PRODUCT_UUID,
            qty=2.0, unit_price=75.0, subtotal=150.0,
        )
        count = db.execute(
            "SELECT COUNT(*) FROM detalles_venta WHERE venta_id=?", (sid,)
        ).fetchone()[0]
        assert count == 1

    def test_get_by_id_returns_dict(self, sales_repo):
        sid, _ = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="x", client_id=CLIENT_UUID,
            subtotal=200.0, discount=10.0, total=190.0,
            payment_method="Tarjeta", amount_paid=190.0,
            operation_id=new_uuid(),
        )
        row = sales_repo.get_by_id(sid)
        assert row is not None
        assert row["total"] == pytest.approx(190.0)
        assert row["forma_pago"] == "Tarjeta"

    def test_get_by_id_nonexistent_returns_none(self, sales_repo):
        assert sales_repo.get_by_id("nonexistent-uuid") is None

    def test_get_by_folio(self, sales_repo):
        sid, folio = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="y", client_id=None,
            subtotal=300.0, discount=0.0, total=300.0,
            payment_method="Efectivo", amount_paid=300.0,
            operation_id=new_uuid(),
        )
        row = sales_repo.get_by_folio(folio)
        assert row is not None
        assert row["id"] == sid

    def test_get_by_operation_id(self, sales_repo):
        op_id = new_uuid()
        sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="z", client_id=None,
            subtotal=400.0, discount=0.0, total=400.0,
            payment_method="Efectivo", amount_paid=400.0,
            operation_id=op_id,
        )
        row = sales_repo.get_by_operation_id(op_id)
        assert row is not None
        assert row["total"] == pytest.approx(400.0)

    def test_get_by_operation_id_missing_returns_none(self, sales_repo):
        assert sales_repo.get_by_operation_id("does-not-exist") is None

    def test_cancel_sale_marks_cancelled(self, sales_repo, db):
        sid, _ = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="mgr", client_id=None,
            subtotal=100.0, discount=0.0, total=100.0,
            payment_method="Efectivo", amount_paid=100.0,
            operation_id=new_uuid(),
        )
        sales_repo.cancel_sale(sid, reason="Error de cliente")
        row = db.execute("SELECT estado FROM ventas WHERE id=?", (sid,)).fetchone()
        assert row["estado"] == "cancelada"

    def test_get_items_returns_all_items(self, sales_repo):
        sid, _ = sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="x", client_id=None,
            subtotal=175.0, discount=0.0, total=175.0,
            payment_method="Efectivo", amount_paid=175.0,
            operation_id=new_uuid(),
        )
        sales_repo.save_sale_item(sid, PRODUCT_UUID,  2.0, 50.0, 100.0)
        sales_repo.save_sale_item(sid, PRODUCT2_UUID, 1.0, 75.0, 75.0)
        items = sales_repo.get_items(sid)
        assert len(items) == 2

    def test_get_today_returns_todays_sales(self, sales_repo):
        sales_repo.create_sale(
            branch_id=BRANCH_UUID, user="cajero", client_id=None,
            subtotal=500.0, discount=0.0, total=500.0,
            payment_method="Efectivo", amount_paid=500.0,
            operation_id=new_uuid(),
        )
        rows = sales_repo.get_today(branch_id=BRANCH_UUID)
        assert len(rows) >= 1
        assert all(r["estado"] != "cancelada" for r in rows)
        assert not str(bid).isdigit(), f"branch_id debe ser UUID, no entero: {bid}"
