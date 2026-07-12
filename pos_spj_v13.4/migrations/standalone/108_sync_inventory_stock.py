"""Migration 108 — backfill inventory_stock from inventario_actual.

Root cause fix: UnifiedInventoryService (used by Producción) writes to
inventario_actual but NOT to inventory_stock.  InventoryQueryService (used by
Inventario UI) reads inventory_stock.  Existing databases have stock in
inventario_actual that was never mirrored to inventory_stock, causing the
Inventario module to show 0 / stale values for products whose stock was set
by production or by the legacy purchase path.

This migration:
  1. Ensures inventory_stock table exists with correct schema.
  2. Backfills inventory_stock from inventario_actual for every
     (product_id, sucursal_id) row that has no entry in inventory_stock yet,
     or whose quantity differs from inventario_actual.cantidad.
  3. Backfills any remaining products from productos.existencia into
     inventory_stock for branch 1 (global fallback), only when no branch row
     exists at all.

Fully idempotent — safe to run multiple times.
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.108")


def _tbl(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _col(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def run(conn: sqlite3.Connection) -> None:
    logger.info("108: syncing inventory_stock from inventario_actual …")

    # ── 1. Ensure inventory_stock exists ─────────────────────────────────────
    if not _tbl(conn, "inventory_stock"):
        conn.execute("""
            CREATE TABLE inventory_stock (
                id         TEXT NOT NULL PRIMARY KEY,
                product_id TEXT NOT NULL,
                branch_id  TEXT NOT NULL,
                quantity   REAL    NOT NULL DEFAULT 0,
                unit       TEXT    NOT NULL DEFAULT 'kg',
                updated_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(product_id, branch_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inv_stock_product "
            "ON inventory_stock(product_id, branch_id)"
        )
        logger.info("108: inventory_stock created")

    # ── 2. Backfill from inventario_actual ───────────────────────────────────
    if _tbl(conn, "inventario_actual"):
        rows = conn.execute("""
            SELECT ia.producto_id,
                   ia.sucursal_id,
                   COALESCE(ia.cantidad, 0),
                   COALESCE(p.unidad, 'kg')
            FROM inventario_actual ia
            JOIN productos p ON p.id = ia.producto_id
        """).fetchall()

        synced = 0
        for pid, sid, qty, unit in rows:
            conn.execute("""
                INSERT INTO inventory_stock (product_id, branch_id, quantity, unit, updated_at)
                VALUES (?,?,?,?,datetime('now'))
                ON CONFLICT(product_id, branch_id) DO UPDATE SET
                    quantity   = excluded.quantity,
                    unit       = excluded.unit,
                    updated_at = excluded.updated_at
                WHERE excluded.quantity != inventory_stock.quantity
            """, (pid, sid, qty, unit))
            synced += 1

        logger.info("108: %d inventory_actual rows synced to inventory_stock", synced)
    else:
        logger.warning("108: inventario_actual missing — skipping primary backfill")

    # ── 3. Fallback: products with no branch row at all ──────────────────────
    fallback = conn.execute("""
        SELECT p.id, COALESCE(p.existencia, 0), COALESCE(p.unidad,'kg')
        FROM productos p
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory_stock s WHERE s.product_id = p.id
        )
          AND COALESCE(p.activo, 1) = 1
    """).fetchall()

    for pid, qty, unit in fallback:
        conn.execute("""
            INSERT OR IGNORE INTO inventory_stock
                (product_id, branch_id, quantity, unit, updated_at)
            VALUES (?, 1, ?, ?, datetime('now'))
        """, (pid, qty, unit))

    if fallback:
        logger.info("108: %d products backfilled from productos.existencia", len(fallback))

    conn.commit()
    logger.info("108: done")
