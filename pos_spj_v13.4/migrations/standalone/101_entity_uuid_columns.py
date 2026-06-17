"""Add uuid TEXT columns to core entity tables (incremental UUID preparation).

This migration adds a ``uuid`` column to tables that are targeted by the
full UUID cutover (migration 200). The column is nullable TEXT so that:

  * Existing rows receive a generated UUIDv7 backfill.
  * New rows written by updated code can store their UUIDv7 identity here
    immediately, before the full atomic cutover replaces the INTEGER PK.
  * UUID-checking guards in repository code will find the column present and
    no longer raise RuntimeError on startup.

This is NOT the atomic cutover. The INTEGER PRIMARY KEY columns are left
intact so that legacy code that still uses lastrowid continues to work.
Migration 200 will perform the full replacement once all callers are updated.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Tables that need a uuid column now.  Only tables whose repository layer
# already generates UUIDs or whose UUID guard is active are listed here.
# Extend the list as more modules are migrated.
_TARGET_TABLES = [
    "sucursales",
    "productos",
    "clientes",
    "usuarios",
]


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def run(conn: sqlite3.Connection) -> None:
    from backend.shared.ids import new_uuid  # local import to avoid circular deps

    for table in _TARGET_TABLES:
        if not _table_exists(conn, table):
            logger.debug("101: table %s does not exist, skipping", table)
            continue

        if not _column_exists(conn, table, "uuid"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
            logger.info("101: added uuid column to %s", table)

        # Backfill existing rows that have no uuid yet
        null_rows = conn.execute(
            f"SELECT id FROM {table} WHERE uuid IS NULL"  # noqa: S608
        ).fetchall()
        if null_rows:
            for (row_id,) in null_rows:
                conn.execute(
                    f"UPDATE {table} SET uuid = ? WHERE id = ?",  # noqa: S608
                    (new_uuid(), row_id),
                )
            logger.info("101: backfilled %d uuid values in %s", len(null_rows), table)

    conn.commit()
    logger.info("101: entity_uuid_columns migration complete")
