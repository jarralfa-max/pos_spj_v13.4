# migrations/m050_hardware_config_canonical.py
"""Canonical hardware configuration schema.

Ensures all hardware-related modules share the same source of truth:
``hardware_config``. The legacy assumed table ``configuraciones_hardware`` is
not created here. If it exists in an older DB, its rows are imported into the
canonical table as a one-time compatibility bridge.
"""
from __future__ import annotations

import json
import sqlite3

version = 50
description = "canonical hardware_config schema and default rows"


DEFAULT_TYPES = {
    "ticket": "Impresora de tickets",
    "etiquetas": "Impresora de etiquetas",
    "bascula": "Báscula",
    "cajon": "Cajón de dinero",
    "scanner": "Escáner",
    "red": "Red",
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hardware_config (
            tipo TEXT NOT NULL PRIMARY KEY,
            nombre TEXT NOT NULL,
            driver TEXT,
            puerto TEXT,
            configuraciones TEXT,
            activo INTEGER DEFAULT 1,
            sucursal_id TEXT,
            fecha_actualizacion DATETIME DEFAULT (datetime('now'))
        )
        """
    )


def _seed_defaults(conn: sqlite3.Connection) -> None:
    for tipo, nombre in DEFAULT_TYPES.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO hardware_config(tipo, nombre, activo, configuraciones)
            VALUES (?, ?, 1, '{}')
            """,
            (tipo, nombre),
        )


def _migrate_legacy(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "configuraciones_hardware"):
        return
    rows = conn.execute("SELECT tipo, clave, valor FROM configuraciones_hardware").fetchall()
    grouped = {}
    for tipo, clave, valor in rows:
        target = "ticket" if str(tipo) in {"ticket", "impresora"} else str(tipo)
        if target in {"impresora_etiquetas", "label", "labels"}:
            target = "etiquetas"
        grouped.setdefault(target, {})[str(clave)] = valor
    for tipo, cfg in grouped.items():
        conn.execute(
            """
            INSERT INTO hardware_config(tipo, nombre, activo, configuraciones)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(tipo) DO UPDATE SET
                configuraciones=excluded.configuraciones,
                activo=1,
                fecha_actualizacion=datetime('now')
            """,
            (tipo, DEFAULT_TYPES.get(tipo, tipo), json.dumps(cfg, ensure_ascii=False)),
        )


def up(conn: sqlite3.Connection) -> None:
    _ensure_schema(conn)
    _seed_defaults(conn)
    _migrate_legacy(conn)
    conn.commit()
