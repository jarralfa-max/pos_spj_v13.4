"""Migration 105 — ensure movimientos_inventario exists.

The table is defined in m000_base_schema but may be absent in databases
created before that definition was added, or when the schema bootstrap
was skipped.  This migration is fully idempotent.
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.105")


def _tbl(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _col(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _add_col(conn: sqlite3.Connection, table: str, col: str, definition: str) -> None:
    if not _col(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        logger.info("105: added column %s.%s", table, col)


def run(conn: sqlite3.Connection) -> None:
    logger.info("105: ensuring movimientos_inventario exists …")

    conn.execute("PRAGMA journal_mode=WAL")

    if not _tbl(conn, "movimientos_inventario"):
        conn.execute("""
            CREATE TABLE movimientos_inventario (
                id                  TEXT NOT NULL PRIMARY KEY,
                uuid                TEXT,
                producto_id         TEXT,
                tipo                TEXT,
                tipo_movimiento     TEXT,
                tipo_movimiento_v2  TEXT,
                cantidad            REAL,
                existencia_anterior REAL DEFAULT 0,
                existencia_nueva    REAL DEFAULT 0,
                costo_unitario      REAL DEFAULT 0,
                costo_total         REAL DEFAULT 0,
                descripcion         TEXT,
                referencia          TEXT,
                referencia_id       TEXT,
                referencia_tipo     TEXT,
                nota                TEXT,
                proveedor_id        TEXT,
                operation_id        TEXT,
                batch_id            TEXT,
                bib_id              TEXT,
                usuario             TEXT,
                sucursal_id         TEXT,
                lote_id             TEXT,
                merma_motivo        TEXT,
                fecha               DATETIME DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mov_inv_producto "
            "ON movimientos_inventario(producto_id, fecha)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_movimientos_inv_lote "
            "ON movimientos_inventario(lote_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mov_inv_sucursal "
            "ON movimientos_inventario(sucursal_id)"
        )
        logger.info("105: movimientos_inventario created with indexes")
    else:
        # Table exists — ensure optional columns added by later migrations are present
        _add_col(conn, "movimientos_inventario", "lote_id",      "TEXT")
        _add_col(conn, "movimientos_inventario", "merma_motivo",  "TEXT")
        # (Plan B) movimientos_inventario.id ES el UUID; sin columna uuid dual.
        _add_col(conn, "movimientos_inventario", "referencia_id", "INTEGER")
        _add_col(conn, "movimientos_inventario", "operation_id",  "TEXT")
        logger.info("105: movimientos_inventario already exists — columns verified")

    conn.commit()
    logger.info("105: done")
