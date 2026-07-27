"""Incrementally complete existing inventory_movements tables.

Migration 098 creates the canonical table for fresh databases, but older
installations may already have inventory_movements. Because 098 uses
CREATE TABLE IF NOT EXISTS, SQLite leaves those existing tables unchanged.
This migration adds the canonical columns idempotently and backfills safe
values for legacy rows.
"""

from __future__ import annotations

import sqlite3


REQUIRED_COLUMNS: dict[str, str] = {
    "operation_id": "TEXT",
    "stock_before": "REAL DEFAULT 0",
    "stock_after": "REAL DEFAULT 0",
    "unit": "TEXT",
    "source_module": "TEXT",
    "reference_type": "TEXT",
    "reference_id": "TEXT",
    "reason": "TEXT",
    "user_name": "TEXT",
    "created_at": "TEXT",
}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(inventory_movements)").fetchall()}


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    existing = _columns(conn)
    for column, ddl in REQUIRED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE inventory_movements ADD COLUMN {column} {ddl}")
            existing.add(column)


def _backfill(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE inventory_movements SET source_module='legacy' WHERE source_module IS NULL OR source_module='' ")
    conn.execute("UPDATE inventory_movements SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL OR created_at='' ")
    conn.execute("UPDATE inventory_movements SET operation_id='legacy-' || id WHERE operation_id IS NULL OR operation_id='' ")
    conn.execute("UPDATE inventory_movements SET stock_before=0 WHERE stock_before IS NULL")
    conn.execute("UPDATE inventory_movements SET stock_after=0 WHERE stock_after IS NULL")


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_movements_product_branch "
        "ON inventory_movements(product_id, branch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_movements_operation "
        "ON inventory_movements(operation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_movements_created_at "
        "ON inventory_movements(created_at)"
    )


def run(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "inventory_movements"):
        return
    _add_missing_columns(conn)
    _backfill(conn)
    _ensure_indexes(conn)
    conn.commit()


up = run
