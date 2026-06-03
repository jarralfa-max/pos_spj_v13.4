"""095_rrhh_identity_links.py — RRHH labor identity consolidation.

Adds nullable links from operational identities (``usuarios`` and ``drivers``)
to the canonical employee table (``personal``). The migration is intentionally
additive and idempotent so existing PyQt screens keep working while users and
drivers are linked to employees through application services.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "RRHH nullable identity links for usuarios and drivers"


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
    if _table_exists(conn, "usuarios"):
        _ensure_column(conn, "usuarios", "personal_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usuarios_personal_id ON usuarios(personal_id)"
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
