"""Migration 106 — ensure inventario_actual and branch_inventory exist.

Databases created before m000_base_schema included these tables, or where
the schema bootstrap was incomplete, fail at runtime whenever the inventory
service tries to INSERT or UPDATE stock after a production run or sale.

This migration is fully idempotent.
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.106")


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
        logger.info("106: added column %s.%s", table, col)


def run(conn: sqlite3.Connection) -> None:
    logger.info("106: ensuring inventario_actual and branch_inventory exist …")

    # ── inventario_actual ─────────────────────────────────────────────────────
    if not _tbl(conn, "inventario_actual"):
        conn.execute("""
            CREATE TABLE inventario_actual (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id          INTEGER NOT NULL,
                sucursal_id          INTEGER NOT NULL,
                cantidad             REAL    NOT NULL DEFAULT 0,
                costo_promedio       REAL    DEFAULT 0,
                ultima_actualizacion TEXT    DEFAULT (datetime('now')),
                UNIQUE(producto_id, sucursal_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inv_actual_prod "
            "ON inventario_actual(producto_id)"
        )
        logger.info("106: inventario_actual created")
    else:
        _add_col(conn, "inventario_actual", "costo_promedio", "REAL DEFAULT 0")
        _add_col(conn, "inventario_actual", "ultima_actualizacion",
                 "TEXT DEFAULT (datetime('now'))")
        logger.info("106: inventario_actual already exists — columns verified")

    # ── inventario_diario ─────────────────────────────────────────────────────
    if not _tbl(conn, "inventario_diario"):
        conn.execute("""
            CREATE TABLE inventario_diario (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha       DATE    NOT NULL,
                producto_id INTEGER NOT NULL,
                sucursal_id INTEGER NOT NULL,
                cantidad    REAL    NOT NULL DEFAULT 0,
                valor       REAL    NOT NULL DEFAULT 0,
                updated_at  TEXT    DEFAULT (datetime('now')),
                UNIQUE(fecha, producto_id, sucursal_id)
            )
        """)
        logger.info("106: inventario_diario created")

    # ── branch_inventory ──────────────────────────────────────────────────────
    if not _tbl(conn, "branch_inventory"):
        conn.execute("""
            CREATE TABLE branch_inventory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id  INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                batch_id   INTEGER,
                quantity   REAL    NOT NULL DEFAULT 0,
                updated_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(branch_id, product_id, batch_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_branch_inv_product "
            "ON branch_inventory(product_id, branch_id)"
        )
        logger.info("106: branch_inventory created")
    else:
        _add_col(conn, "branch_inventory", "batch_id", "INTEGER")
        _add_col(conn, "branch_inventory", "updated_at",
                 "TEXT DEFAULT (datetime('now'))")
        logger.info("106: branch_inventory already exists — columns verified")

    conn.commit()
    logger.info("106: done")
