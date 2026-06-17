"""Migration 103 — add sucursal_uuid to happy_hour_rules and backfill.

Context: Configuracion module guards check for happy_hour_rules.sucursal_uuid
before operating. This migration adds the column idempotently, backfills it
from sucursal_id→sucursales.uuid (migration 101 already added sucursales.uuid),
and creates an index. Safe to run multiple times.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

MIGRATION_ID = "103"
TABLE = "happy_hour_rules"
COLUMN = "sucursal_uuid"


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _tbl_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def run(conn: sqlite3.Connection) -> None:
    if not _tbl_exists(conn, TABLE):
        logger.info("[%s] %s does not exist — skipping", MIGRATION_ID, TABLE)
        return

    try:
        # Step 1: add sucursal_uuid column if missing
        if not _col_exists(conn, TABLE, COLUMN):
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT")
            logger.info("[%s] added column %s.%s", MIGRATION_ID, TABLE, COLUMN)
        else:
            logger.info("[%s] column %s.%s already exists — skipping ADD", MIGRATION_ID, TABLE, COLUMN)

        # Step 2: backfill from sucursal_id → sucursales.uuid (when both exist)
        has_sucursal_id = _col_exists(conn, TABLE, "sucursal_id")
        has_branch_uuid = _tbl_exists(conn, "sucursales") and _col_exists(conn, "sucursales", "uuid")

        if has_sucursal_id and has_branch_uuid:
            conn.execute(
                f"""
                UPDATE {TABLE}
                SET {COLUMN} = (
                    SELECT s.uuid
                    FROM sucursales s
                    WHERE s.id = {TABLE}.sucursal_id
                )
                WHERE {COLUMN} IS NULL
                  AND sucursal_id IS NOT NULL
                """
            )
            backfilled = conn.execute("SELECT changes()").fetchone()[0]
            logger.info("[%s] backfilled %d rows in %s.%s", MIGRATION_ID, backfilled, TABLE, COLUMN)
        else:
            logger.info(
                "[%s] skipping backfill — sucursal_id=%s, sucursales.uuid=%s",
                MIGRATION_ID, has_sucursal_id, has_branch_uuid,
            )

        # Step 3: create index (idempotent)
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_{COLUMN} ON {TABLE}({COLUMN})"
        )
        logger.info("[%s] index idx_%s_%s ensured", MIGRATION_ID, TABLE, COLUMN)

        conn.commit()
        logger.info("[%s] migration complete", MIGRATION_ID)

    except Exception:
        conn.rollback()
        logger.exception("[%s] migration FAILED — rolled back", MIGRATION_ID)
        raise
