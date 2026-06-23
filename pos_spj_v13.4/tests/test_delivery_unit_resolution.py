"""Unit resolution for delivery items — weighable vs countable guard.

Verifies:
- get_order_items resolves product unit from productos table (not delivery_items.unidad default)
- Non-weighable units (pza, caja, unidad) are excluded from var_items filter
- Weighable units (kg, g, L) are included in var_items filter
- LEGACY_UNIT_MAP + WEIGHABLE_UNITS is the single source of truth for the filter
"""
from __future__ import annotations
import sqlite3
import pytest
from core.delivery.domain.value_objects import (
    WEIGHABLE_UNITS, UnitCode, resolve_unit,
)
from core.services.delivery_service import DeliveryService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn_with_items(product_unit: str, item_unidad: str = "kg") -> sqlite3.Connection:
    """Create in-memory DB with one delivery order + one item.

    item_unidad simulates the legacy default stored in delivery_items.
    product_unit is the correct unit on the producto row.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(f"""
        CREATE TABLE delivery_orders(
            id INTEGER PRIMARY KEY, estado TEXT DEFAULT 'pendiente'
        );
        CREATE TABLE productos(
            id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT
        );
        CREATE TABLE delivery_items(
            id INTEGER PRIMARY KEY, delivery_id INTEGER, nombre TEXT,
            cantidad REAL, precio_unitario REAL, subtotal REAL,
            unidad TEXT, producto_id INTEGER,
            requested_qty REAL, prepared_qty REAL, final_qty REAL,
            prepared_by TEXT, prepared_at TEXT, adjustment_reason TEXT,
            tolerance_exceeded INTEGER DEFAULT 0,
            pending_prepared_qty REAL, pending_subtotal REAL,
            adjustment_status TEXT, adjustment_requested_at TEXT,
            adjustment_responded_at TEXT, adjustment_response TEXT,
            tolerance_units REAL DEFAULT 0.2
        );
        INSERT INTO delivery_orders VALUES(1, 'preparacion');
        INSERT INTO productos VALUES(10, 'Piña Enchilada PREMIER', '{product_unit}');
        INSERT INTO delivery_items(id, delivery_id, nombre, cantidad, precio_unitario,
            subtotal, unidad, producto_id, requested_qty)
        VALUES(1, 1, 'Piña Enchilada PREMIER', 5, 185, 925, '{item_unidad}', 10, 5);
    """)
    return conn


def _is_weighable(unit_str: str) -> bool:
    """Canonical filter used in ejecutar_accion."""
    return resolve_unit(unit_str) in WEIGHABLE_UNITS


# ── Unit map tests ────────────────────────────────────────────────────────────

def test_kg_is_weighable():
    assert _is_weighable("kg") is True

def test_g_is_weighable():
    assert _is_weighable("g") is True

def test_liter_is_weighable():
    assert _is_weighable("L") is True

def test_pza_is_not_weighable():
    assert _is_weighable("pza") is False

def test_pieza_is_not_weighable():
    assert _is_weighable("pieza") is False

def test_caja_is_not_weighable():
    assert _is_weighable("caja") is False

def test_unidad_is_not_weighable():
    assert _is_weighable("unidad") is False

def test_empty_string_defaults_to_piece_not_weighable():
    assert _is_weighable("") is False


# ── get_order_items unit resolution ──────────────────────────────────────────

def test_product_unit_overrides_item_default():
    """Canonical fix: productos.unidad takes precedence over delivery_items.unidad (legacy "kg")."""
    conn = _conn_with_items(product_unit="pza", item_unidad="kg")
    svc = DeliveryService(conn)
    items = svc.get_order_items(1)
    assert len(items) == 1
    assert items[0]["unidad"] == "pza", (
        "productos.unidad must override the legacy 'kg' stored in delivery_items.unidad"
    )

def test_item_unit_fallback_when_no_product_row():
    """When producto row is absent, falls back to delivery_items.unidad."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE delivery_orders(id INTEGER PRIMARY KEY, estado TEXT DEFAULT 'pendiente');
        CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT);
        CREATE TABLE delivery_items(
            id INTEGER PRIMARY KEY, delivery_id INTEGER, nombre TEXT,
            cantidad REAL, precio_unitario REAL, subtotal REAL,
            unidad TEXT, producto_id INTEGER,
            requested_qty REAL, prepared_qty REAL, final_qty REAL,
            prepared_by TEXT, prepared_at TEXT, adjustment_reason TEXT,
            tolerance_exceeded INTEGER DEFAULT 0,
            pending_prepared_qty REAL, pending_subtotal REAL,
            adjustment_status TEXT, adjustment_requested_at TEXT,
            adjustment_responded_at TEXT, adjustment_response TEXT,
            tolerance_units REAL DEFAULT 0.2
        );
        INSERT INTO delivery_orders VALUES(1, 'preparacion');
        INSERT INTO delivery_items(id, delivery_id, nombre, cantidad, unidad, producto_id, requested_qty)
        VALUES(1, 1, 'Alas', 5, 'kg', NULL, 5);
    """)
    svc = DeliveryService(conn)
    items = svc.get_order_items(1)
    assert items[0]["unidad"] == "kg"

def test_countable_product_not_in_var_items():
    """A product with pza unit must NOT appear in var_items (no dialog should open)."""
    conn = _conn_with_items(product_unit="pza", item_unidad="kg")
    svc = DeliveryService(conn)
    items = svc.get_order_items(1)
    var_items = [it for it in items if _is_weighable(it.get("unidad", ""))]
    assert var_items == [], "pza product must not trigger weight adjustment dialog"

def test_kg_product_in_var_items():
    """A product with kg unit MUST appear in var_items."""
    conn = _conn_with_items(product_unit="kg", item_unidad="kg")
    svc = DeliveryService(conn)
    items = svc.get_order_items(1)
    var_items = [it for it in items if _is_weighable(it.get("unidad", ""))]
    assert len(var_items) == 1


def test_name_lookup_resolves_unit_when_producto_id_null():
    """WhatsApp items (producto_id=NULL) resolve unit from productos by name."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE delivery_orders(id INTEGER PRIMARY KEY, estado TEXT DEFAULT 'pendiente');
        CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE delivery_items(
            id INTEGER PRIMARY KEY, delivery_id INTEGER, nombre TEXT,
            cantidad REAL, precio_unitario REAL DEFAULT 0, subtotal REAL DEFAULT 0,
            unidad TEXT, producto_id INTEGER,
            requested_qty REAL DEFAULT 0, prepared_qty REAL, final_qty REAL,
            prepared_by TEXT, prepared_at TEXT, adjustment_reason TEXT,
            tolerance_exceeded INTEGER DEFAULT 0,
            pending_prepared_qty REAL, pending_subtotal REAL,
            adjustment_status TEXT, adjustment_requested_at TEXT,
            adjustment_responded_at TEXT, adjustment_response TEXT,
            tolerance_units REAL DEFAULT 0.2
        );
        INSERT INTO delivery_orders VALUES(1, 'preparacion');
        INSERT INTO productos VALUES(10, 'Piña Enchilada PREMIER', 'pza', 1);
        -- WhatsApp item: producto_id is NULL, unidad defaulted to 'kg'
        INSERT INTO delivery_items(id, delivery_id, nombre, cantidad, unidad, producto_id, requested_qty)
        VALUES(1, 1, 'Piña Enchilada PREMIER', 5, 'kg', NULL, 5);
    """)
    svc = DeliveryService(conn)
    items = svc.get_order_items(1)
    assert items[0]["unidad"] == "pza", "name-based lookup must replace legacy 'kg' with product's real unit"
    var_items = [it for it in items if _is_weighable(it.get("unidad", ""))]
    assert var_items == [], "pza product must not appear in var_items even when stored as 'kg'"
