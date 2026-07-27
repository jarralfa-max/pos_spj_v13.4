# migrations/standalone/088_delivery_adjustment_approval.py
"""Aprobación de cliente para ajustes de peso/cantidad en Delivery.

Reglas:
- Ajuste solo aplica en estado preparacion.
- Tolerancia por unidades, no porcentaje: +-0.2 unidades.
- Si excede tolerancia, queda pendiente de aceptación del cliente.
- No se permite avanzar a en_ruta/entregado mientras haya ajuste pendiente.
"""
from __future__ import annotations

import sqlite3

version = 88
description = "delivery adjustment approval"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    if not _table_exists(conn, table_name):
        return False
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(r[1] == column_name for r in rows)


def _ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    col_name = definition.strip().split()[0]
    if not _table_exists(conn, table):
        return
    if not _column_exists(conn, table, col_name):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def up(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "delivery_items"):
        _ensure_column(conn, "delivery_items", "pending_prepared_qty REAL")
        _ensure_column(conn, "delivery_items", "pending_subtotal REAL")
        _ensure_column(conn, "delivery_items", "adjustment_status TEXT DEFAULT 'none'")
        _ensure_column(conn, "delivery_items", "adjustment_requested_at DATETIME")
        _ensure_column(conn, "delivery_items", "adjustment_responded_at DATETIME")
        _ensure_column(conn, "delivery_items", "adjustment_response TEXT")
        _ensure_column(conn, "delivery_items", "adjustment_token TEXT")
        _ensure_column(conn, "delivery_items", "tolerance_units REAL DEFAULT 0.2")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_status ON delivery_items(adjustment_status, delivery_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_token ON delivery_items(adjustment_token)")

    if _table_exists(conn, "delivery_orders"):
        _ensure_column(conn, "delivery_orders", "adjustment_pending INTEGER DEFAULT 0")
        _ensure_column(conn, "delivery_orders", "adjustment_blocked_state TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_delivery_orders_adjustment_pending ON delivery_orders(adjustment_pending, estado)")

    try:
        conn.commit()
    except Exception:
        pass


run = up
