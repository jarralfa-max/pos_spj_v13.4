from __future__ import annotations

import importlib
import sqlite3


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    return {str(row[1]): str(row[2]).upper() for row in conn.execute(f"PRAGMA table_info({table})")}


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA index_list({table})")}


def test_canonical_inventory_migration_creates_required_tables_indexes_and_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    migration = importlib.import_module("migrations.standalone.098_canonical_inventory")

    migration.run(conn)
    migration.run(conn)

    stock_columns = _columns(conn, "inventory_stock")
    movement_columns = _columns(conn, "inventory_movements")

    assert stock_columns["id"] == "INTEGER"
    assert stock_columns["product_id"] == "INTEGER"
    assert stock_columns["branch_id"] == "INTEGER"
    assert stock_columns["quantity"] == "REAL"
    assert stock_columns["unit"] == "TEXT"
    assert stock_columns["updated_at"] == "TEXT"

    assert movement_columns["operation_id"] == "TEXT"
    assert movement_columns["product_id"] == "INTEGER"
    assert movement_columns["branch_id"] == "INTEGER"
    assert movement_columns["movement_type"] == "TEXT"
    assert movement_columns["stock_before"] == "REAL"
    assert movement_columns["stock_after"] == "REAL"
    assert movement_columns["source_module"] == "TEXT"

    assert "idx_inventory_stock_product_branch" in _indexes(conn, "inventory_stock")
    assert "idx_inventory_stock_branch" in _indexes(conn, "inventory_stock")
    assert "idx_inventory_movements_product_branch" in _indexes(conn, "inventory_movements")
    assert "idx_inventory_movements_operation" in _indexes(conn, "inventory_movements")
    assert "idx_inventory_movements_created_at" in _indexes(conn, "inventory_movements")
