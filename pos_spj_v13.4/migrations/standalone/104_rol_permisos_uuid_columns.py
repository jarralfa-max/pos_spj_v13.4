"""Migration 104 — add rol_uuid to rol_permisos and sucursal_uuid to cierre_mensual.

These columns are required by the Configuracion module's permission and
monthly-closing services. Both are added idempotently with backfill:
  - rol_permisos.rol_uuid    ← roles.uuid via rol_id → roles.id join
  - cierre_mensual.sucursal_uuid ← sucursales.uuid via sucursal_id → sucursales.id
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

MIGRATION_ID = "104"


def _col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _tbl_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def _add_and_backfill(
    conn: sqlite3.Connection,
    table: str,
    new_col: str,
    src_col: str,
    ref_table: str,
    ref_src: str,
    ref_dst: str,
) -> None:
    """Add new_col to table and backfill via a lookup join."""
    if not _tbl_exists(conn, table):
        logger.info("[%s] %s does not exist — skipping", MIGRATION_ID, table)
        return

    if not _col_exists(conn, table, new_col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {new_col} TEXT")
        logger.info("[%s] added column %s.%s", MIGRATION_ID, table, new_col)

    has_src_col = _col_exists(conn, table, src_col)
    has_ref_uuid = _tbl_exists(conn, ref_table) and _col_exists(conn, ref_table, ref_dst)

    if has_src_col and has_ref_uuid:
        conn.execute(
            f"""
            UPDATE {table}
            SET {new_col} = (
                SELECT r.{ref_dst}
                FROM {ref_table} r
                WHERE r.{ref_src} = {table}.{src_col}
            )
            WHERE {new_col} IS NULL
              AND {src_col} IS NOT NULL
            """
        )
        updated = conn.execute("SELECT changes()").fetchone()[0]
        logger.info("[%s] backfilled %d rows in %s.%s", MIGRATION_ID, updated, table, new_col)

    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_{new_col} ON {table}({new_col})"
    )


def run(conn: sqlite3.Connection) -> None:
    try:
        # rol_permisos.rol_uuid ← roles.uuid via rol_id → roles.id
        _add_and_backfill(
            conn,
            table="rol_permisos",
            new_col="rol_uuid",
            src_col="rol_id",
            ref_table="roles",
            ref_src="id",
            ref_dst="uuid",
        )

        # cierre_mensual.sucursal_uuid ← sucursales.uuid via sucursal_id → sucursales.id
        _add_and_backfill(
            conn,
            table="cierre_mensual",
            new_col="sucursal_uuid",
            src_col="sucursal_id",
            ref_table="sucursales",
            ref_src="id",
            ref_dst="uuid",
        )

        conn.commit()
        logger.info("[%s] migration complete", MIGRATION_ID)

    except Exception:
        conn.rollback()
        logger.exception("[%s] migration FAILED — rolled back", MIGRATION_ID)
        raise
