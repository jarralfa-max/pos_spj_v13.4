"""Migration 107 — add missing columns to productos used by production cost service.

ProductionCostService writes to productos.costo and productos.costo_promedio.
These columns are absent from the base schema definition and were never added
by a prior migration, causing OperationalError: no such column: costo.

This migration is fully idempotent.
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.107")


def _col(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _add_col(conn: sqlite3.Connection, table: str, col: str, definition: str) -> None:
    if not _col(conn, table, col):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        logger.info("107: added column %s.%s", table, col)
    else:
        logger.debug("107: column %s.%s already exists — skipped", table, col)


def _tbl(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def run(conn: sqlite3.Connection) -> None:
    logger.info("107: ensuring cost columns exist on productos and related tables …")

    if _tbl(conn, "productos"):
        # Cost columns used by ProductionCostService
        _add_col(conn, "productos", "costo",          "REAL DEFAULT 0")
        _add_col(conn, "productos", "costo_promedio",  "REAL DEFAULT 0")
        # Additional columns referenced in production / inventory flows
        _add_col(conn, "productos", "tipo_producto",   "TEXT DEFAULT 'simple'")
        _add_col(conn, "productos", "es_compuesto",    "INTEGER DEFAULT 0")
        _add_col(conn, "productos", "es_subproducto",  "INTEGER DEFAULT 0")
        _add_col(conn, "productos", "precio_minimo",   "REAL DEFAULT 0")
        # (Plan B) productos.id ES el UUID; sin columna uuid dual.
    else:
        logger.warning("107: productos table does not exist — skipping (run m000 first)")

    conn.commit()
    logger.info("107: done")
