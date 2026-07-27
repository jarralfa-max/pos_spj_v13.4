# migrations/standalone/086_whatsapp_order_sales_columns.py
"""Extiende ventas para pedidos creados desde WhatsApp.

El microservicio WhatsApp crea pedidos pendientes en `ventas` para que el POS
los pueda ver/notificar y luego confirmar, pesar, ajustar o cobrar.

Esta migración es aditiva e idempotente. No modifica el flujo normal de ventas
POS; solo agrega columnas usadas por pedidos entrantes de WhatsApp.
"""
from __future__ import annotations

import sqlite3

version = 86
description = "whatsapp order sales columns"


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
    if not _table_exists(conn, "ventas"):
        return

    # Metadatos de pedidos entrantes WhatsApp / delivery.
    _ensure_column(conn, "ventas", "tipo_entrega TEXT DEFAULT 'sucursal'")
    _ensure_column(conn, "ventas", "direccion_entrega TEXT")
    _ensure_column(conn, "ventas", "fecha_entrega_programada DATETIME")
    _ensure_column(conn, "ventas", "notas TEXT")
    _ensure_column(conn, "ventas", "canal TEXT DEFAULT 'pos'")
    _ensure_column(conn, "ventas", "anticipo_pagado REAL DEFAULT 0")
    _ensure_column(conn, "ventas", "venta_origen TEXT")

    # Compatibilidad con registros existentes.
    conn.execute("UPDATE ventas SET canal='pos' WHERE canal IS NULL OR canal='' ")
    conn.execute("UPDATE ventas SET tipo_entrega='sucursal' WHERE tipo_entrega IS NULL OR tipo_entrega='' ")

    # Índices para que el POS detecte rápido pedidos pendientes WA.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_canal_estado ON ventas(canal, estado, fecha)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ventas_wa_pendientes ON ventas(estado, canal, sucursal_id)")

    try:
        conn.commit()
    except Exception:
        pass


run = up
