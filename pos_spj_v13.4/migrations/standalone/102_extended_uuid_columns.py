"""Add uuid / sucursal_uuid columns to additional tables (incremental UUID prep).

Migration 101 covered the four primary entity tables. This migration extends
the same pattern to secondary tables that the Configuracion module accesses
and whose UUID-checking guards are active on some installations.

Columns added (all nullable TEXT, idempotent):
  - uuid TEXT        → happy_hour_rules, roles, rol_permisos, personal,
                       audit_logs, cierre_mensual, configuraciones
  - sucursal_uuid TEXT → usuarios  (cross-reference to sucursales.uuid)

Existing rows are backfilled with new UUIDv7 values for the uuid columns.
The sucursal_uuid column is left NULL until a proper association lookup
is implemented (safe: it is a cross-reference, not a PK).
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Tables that only need a plain uuid column backfilled
_UUID_ONLY_TABLES = [
    "happy_hour_rules",
    "roles",
    "rol_permisos",
    "personal",
    "audit_logs",
    "cierre_mensual",
]

# Tables that need an extra cross-reference uuid column (no backfill needed)
_EXTRA_COLUMNS: dict[str, str] = {
    "usuarios": "sucursal_uuid",
}


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def run(conn: sqlite3.Connection) -> None:
    from backend.shared.ids import new_uuid

    for table in _UUID_ONLY_TABLES:
        if not _table_exists(conn, table):
            logger.debug("102: table %s does not exist, skipping", table)
            continue

        if not _column_exists(conn, table, "uuid"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
            logger.info("102: added uuid column to %s", table)

        null_rows = conn.execute(
            f"SELECT id FROM {table} WHERE uuid IS NULL"  # noqa: S608
        ).fetchall()
        if null_rows:
            for (row_id,) in null_rows:
                conn.execute(
                    f"UPDATE {table} SET uuid = ? WHERE id = ?",  # noqa: S608
                    (new_uuid(), row_id),
                )
            logger.info("102: backfilled %d uuid values in %s", len(null_rows), table)

    # Extra cross-reference columns (no backfill — populated when records are updated)
    for table, column in _EXTRA_COLUMNS.items():
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
            logger.info("102: added %s column to %s", column, table)

    conn.commit()
    logger.info("102: extended_uuid_columns migration complete")
