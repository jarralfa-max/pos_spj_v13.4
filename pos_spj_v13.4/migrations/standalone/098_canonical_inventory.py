"""Create canonical English inventory schema for inventory_stock/kardex."""

from __future__ import annotations

import sqlite3


def run(conn: sqlite3.Connection) -> None:
    """Create canonical inventory tables and indexes idempotently.

    Per the controlled refactor rules, this migration does not migrate legacy
    stock data. The project is in development, so inventory_stock may start
    empty until modules are migrated onto the canonical route.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'unit',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product_id, branch_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            stock_before REAL NOT NULL,
            stock_after REAL NOT NULL,
            unit TEXT,
            source_module TEXT NOT NULL,
            reference_type TEXT,
            reference_id TEXT,
            reason TEXT,
            user_name TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(operation_id, product_id, branch_id, movement_type)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_stock_product_branch "
        "ON inventory_stock(product_id, branch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_stock_branch "
        "ON inventory_stock(branch_id)"
    )
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
    conn.commit()


up = run
