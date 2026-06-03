"""094_rrhh_delivery_cleanup_schema.py — RRHH/Delivery cleanup schema.

Moves UI-created RRHH tables to an idempotent migration and adds optional driver
traceability columns used by the consolidated DriverRepository path.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "RRHH puestos/vacaciones tables and consolidated driver traceability"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    if _table_exists(conn, table) and not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def run(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS puestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vacaciones_personal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personal_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'vacaciones',
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            dias INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'aprobado',
            notas TEXT,
            fecha_registro DATETIME DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vacaciones_personal_estado "
        "ON vacaciones_personal(personal_id, estado, fecha_inicio, fecha_fin)"
    )

    if _table_exists(conn, "drivers"):
        _ensure_column(conn, "drivers", "personal_id INTEGER")
        _ensure_column(conn, "drivers", "source_module TEXT DEFAULT 'delivery'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_drivers_personal_id ON drivers(personal_id)"
        )

    try:
        conn.commit()
    except Exception:
        pass


up = run
