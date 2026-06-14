from __future__ import annotations

import importlib
import sqlite3

from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository


def _legacy_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT)")
    conn.execute("INSERT INTO productos(id, nombre) VALUES (1, 'Pollo')")
    conn.execute(
        """
        CREATE TABLE inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO inventory_movements(product_id, branch_id, movement_type, quantity) "
        "VALUES (1, 1, 'DECREASE', 2)"
    )
    conn.commit()
    return conn


def test_inventory_movements_migration_completes_legacy_table_and_query_works() -> None:
    conn = _legacy_db()
    migration = importlib.import_module("migrations.standalone.100_inventory_movements_incremental_columns")

    migration.run(conn)
    migration.run(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory_movements)").fetchall()}
    for column in {
        "operation_id",
        "stock_before",
        "stock_after",
        "unit",
        "source_module",
        "reference_type",
        "reference_id",
        "reason",
        "user_name",
        "created_at",
    }:
        assert column in columns

    row = conn.execute(
        "SELECT operation_id, source_module, created_at, stock_before, stock_after "
        "FROM inventory_movements WHERE id=1"
    ).fetchone()
    assert row[0] == "legacy-1"
    assert row[1] == "legacy"
    assert row[2]
    assert float(row[3]) == 0.0
    assert float(row[4]) == 0.0

    rows = InventoryQueryService(InventoryRepository(conn)).list_recent_movements(branch_id=1)
    assert len(rows) == 1
    assert rows[0][1] == "Pollo"
    assert rows[0][6] == ""
    assert rows[0][7] == "legacy"
