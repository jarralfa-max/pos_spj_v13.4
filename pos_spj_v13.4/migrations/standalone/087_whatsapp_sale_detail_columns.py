# migrations/standalone/087_whatsapp_sale_detail_columns.py
"""Extiende detalles_venta para pedidos creados desde WhatsApp.

El flujo WhatsApp necesita conservar el nombre visible del producto al momento
del pedido, aunque después cambie el catálogo. Esta migración agrega columnas
aditivas y seguras para compatibilidad con el microservicio.
"""
from __future__ import annotations

import sqlite3

version = 87
description = "whatsapp sale detail columns"


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
    if not _table_exists(conn, "detalles_venta"):
        return

    _ensure_column(conn, "detalles_venta", "nombre TEXT")

    # Backfill: guardar nombre actual del catálogo en detalles existentes.
    try:
        conn.execute("""
            UPDATE detalles_venta
            SET nombre = (
                SELECT p.nombre FROM productos p WHERE p.id = detalles_venta.producto_id
            )
            WHERE (nombre IS NULL OR nombre = '')
              AND producto_id IS NOT NULL
        """)
    except Exception:
        pass

    conn.execute("CREATE INDEX IF NOT EXISTS idx_detalles_venta_venta_id ON detalles_venta(venta_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_detalles_venta_producto_id ON detalles_venta(producto_id)")

    try:
        conn.commit()
    except Exception:
        pass


run = up
