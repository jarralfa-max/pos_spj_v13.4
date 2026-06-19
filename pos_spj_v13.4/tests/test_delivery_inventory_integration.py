"""Integration tests: Delivery↔Inventory stock check at preparacion."""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            existencia REAL DEFAULT 0,
            unidad TEXT DEFAULT 'u',
            stock_minimo REAL DEFAULT 0,
            activo INTEGER DEFAULT 1,
            costo REAL DEFAULT 0
        );
        CREATE TABLE delivery_orders (
            id INTEGER PRIMARY KEY,
            estado TEXT DEFAULT 'pendiente',
            sucursal_id INTEGER DEFAULT 1,
            workflow_type TEXT,
            delivery_type TEXT,
            venta_id INTEGER,
            folio TEXT,
            whatsapp_order_id TEXT,
            cliente_id INTEGER,
            cliente_nombre TEXT,
            cliente_tel TEXT,
            direccion TEXT,
            lat REAL,
            lng REAL,
            notas TEXT,
            total REAL DEFAULT 0,
            usuario TEXT,
            historial_cambios TEXT,
            scheduled_at TEXT,
            source_channel TEXT,
            responsable_entrega TEXT,
            pago_metodo TEXT,
            pago_monto REAL,
            driver_id INTEGER,
            corte_id TEXT,
            fecha_entrega TEXT,
            responsable TEXT
        );
        CREATE TABLE delivery_items (
            id INTEGER PRIMARY KEY,
            delivery_id INTEGER,
            producto_id INTEGER,
            nombre TEXT,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL,
            unidad TEXT DEFAULT 'u',
            adjustment_status TEXT,
            requested_qty REAL,
            prepared_qty REAL,
            final_qty REAL,
            prepared_by TEXT,
            prepared_at TEXT,
            adjustment_reason TEXT,
            tolerance_exceeded INTEGER DEFAULT 0,
            pending_prepared_qty REAL,
            pending_subtotal REAL,
            adjustment_requested_at TEXT,
            adjustment_responded_at TEXT,
            adjustment_response TEXT,
            tolerance_units TEXT
        );
        CREATE TABLE delivery_order_history (
            id INTEGER PRIMARY KEY,
            delivery_id INTEGER,
            estado_anterior TEXT,
            estado_nuevo TEXT,
            usuario TEXT,
            timestamp TEXT,
            reason TEXT,
            metadata TEXT
        );
        INSERT INTO productos VALUES (1, 'Pechuga', 10.0, 'kg', 0, 1, 0);
        INSERT INTO productos VALUES (2, 'Filete',  2.0,  'kg', 0, 1, 0);
        INSERT INTO delivery_orders(id, estado, sucursal_id, workflow_type, direccion, total, usuario)
            VALUES (10, 'pendiente', 1, 'delivery', 'Calle 1', 100, 'test');
        INSERT INTO delivery_orders(id, estado, sucursal_id, workflow_type, direccion, total, usuario)
            VALUES (11, 'pendiente', 1, 'delivery', 'Calle 2', 50,  'test');
        INSERT INTO delivery_items(delivery_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
            VALUES (10, 1, 'Pechuga', 5.0, 20, 100);
        INSERT INTO delivery_items(delivery_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
            VALUES (11, 2, 'Filete',  5.0, 10,  50);
    """)
    return db


def _make_svc(db):
    from core.services.delivery_service import DeliveryService
    return DeliveryService(db)


def test_sufficient_stock_allows_preparacion():
    """Order requesting 5kg where 10kg is available should succeed."""
    db = _make_db()
    svc = _make_svc(db)
    # Product 1 has 10kg available, order 10 requests 5kg — should succeed
    svc.update_status(10, "preparacion", usuario="tester")
    row = db.execute("SELECT estado FROM delivery_orders WHERE id=10").fetchone()
    assert row["estado"] == "preparacion"


def test_insufficient_stock_blocks_preparacion():
    """Order requesting 5kg where only 2kg is available should raise ValueError."""
    db = _make_db()
    svc = _make_svc(db)
    # Product 2 has 2kg, order 11 requests 5kg — should fail
    with pytest.raises(ValueError, match="[Ss]tock|[Ii]nsuficiente|[Dd]isponible"):
        svc.update_status(11, "preparacion", usuario="tester")


def test_inventory_balance_service_reads_from_productos():
    """InventoryBalanceService falls back to productos.existencia when no inventario_actual."""
    from core.services.inventory_balance_service import InventoryBalanceService

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            existencia REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg'
        );
        INSERT INTO productos VALUES (1, 10.0, 'kg');
        INSERT INTO productos VALUES (2,  3.0, 'kg');
    """)
    svc = InventoryBalanceService(db)
    bal = svc.get_balance(product_id="1", branch_id="1")
    assert bal.available_stock == Decimal("10")
    assert bal.branch_id == "1"
    assert bal.product_id == "1"


def test_inventory_balance_raises_on_missing_product_id():
    from core.services.inventory_balance_service import InventoryBalanceService

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    svc = InventoryBalanceService(db)
    with pytest.raises(ValueError, match="product_id"):
        svc.get_balance(product_id=None, branch_id="1")


def test_inventory_balance_raises_on_missing_branch_id():
    from core.services.inventory_balance_service import InventoryBalanceService

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    svc = InventoryBalanceService(db)
    with pytest.raises(ValueError, match="branch_id"):
        svc.get_balance(product_id="1", branch_id=None)


def test_inventory_balance_service_with_inventario_actual():
    """InventoryBalanceService reads from inventario_actual when present (branch-aware)."""
    from core.services.inventory_balance_service import InventoryBalanceService

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            existencia REAL DEFAULT 0,
            unidad TEXT DEFAULT 'kg'
        );
        CREATE TABLE inventario_actual (
            producto_id INTEGER,
            sucursal_id INTEGER,
            cantidad REAL DEFAULT 0,
            costo_promedio REAL DEFAULT 0
        );
        INSERT INTO productos VALUES (1, 999.0, 'kg');
        INSERT INTO inventario_actual VALUES (1, 1, 15.0, 10.0);
    """)
    svc = InventoryBalanceService(db)
    bal = svc.get_balance(product_id=1, branch_id=1)
    # Should read 15.0 from inventario_actual, not 999.0 from productos
    assert bal.physical_stock == Decimal("15")
    assert bal.available_stock == Decimal("15")
