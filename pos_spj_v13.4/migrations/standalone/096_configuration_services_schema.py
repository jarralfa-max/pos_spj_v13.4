"""096_configuration_services_schema.py — configuration schema ownership.

Moves configuration module schema/default bootstrapping out of PyQt and into
migrations so services and UI never create tables at runtime.
"""
from __future__ import annotations

import sqlite3

from backend.shared.ids import new_uuid
from core.module_config import DEFAULT_TOGGLES


def run(conn: sqlite3.Connection) -> None:
    def column_exists(table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row[1]) == column for row in rows)

    def add_column_if_missing(table: str, column_def: str) -> None:
        column_name = column_def.split()[0]
        if not column_exists(table, column_name):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS config_programa_fidelidad (
            id TEXT NOT NULL PRIMARY KEY,
            nombre_programa TEXT,
            puntos_por_peso DECIMAL(10,2) DEFAULT 1.0,
            niveles TEXT,
            requisitos TEXT,
            descuentos TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO config_programa_fidelidad (id, nombre_programa, puntos_por_peso)
        VALUES (1, 'Programa de Puntos', 1.0)
        ON CONFLICT(id) DO NOTHING
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS module_toggles (
            clave TEXT NOT NULL PRIMARY KEY,
            activo INTEGER DEFAULT 1,
            descripcion TEXT DEFAULT ''
        )
        """
    )
    # (Plan B born-clean) Las columnas duales uuid/sucursal_uuid/rol_uuid y su
    # backfill fueron eliminadas: la identidad canónica ya ES id TEXT UUIDv7.
    try:
        conn.commit()
    except Exception:
        pass


up = run
