from __future__ import annotations

import importlib
import sqlite3


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_archive_legacy_inventory_migration_renames_legacy_tables_and_is_idempotent() -> None:
    migration = importlib.import_module("migrations.standalone.099_archive_legacy_inventory_sources")
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL DEFAULT 0);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id INTEGER, sucursal_id INTEGER, cantidad REAL);
        CREATE TABLE branch_inventory (id INTEGER PRIMARY KEY, product_id INTEGER, branch_id INTEGER, quantity REAL);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY, producto_id INTEGER, cantidad REAL);
        INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES (1, 1, 10);
        INSERT INTO branch_inventory(product_id, branch_id, quantity) VALUES (1, 1, 10);
        INSERT INTO movimientos_inventario(producto_id, cantidad) VALUES (1, 10);
        """
    )

    migration.run(conn)
    migration.run(conn)

    tables = _tables(conn)
    assert "inventario_actual" not in tables
    assert "branch_inventory" not in tables
    assert "movimientos_inventario" not in tables
    assert "legacy_inventario_actual" in tables
    assert "legacy_branch_inventory" in tables
    assert "legacy_movimientos_inventario" in tables
    assert "existencia" in _columns(conn, "productos")
    assert conn.execute("SELECT cantidad FROM legacy_inventario_actual").fetchone()[0] == 10
    assert conn.execute("SELECT quantity FROM legacy_branch_inventory").fetchone()[0] == 10
    assert conn.execute("SELECT cantidad FROM legacy_movimientos_inventario").fetchone()[0] == 10


def test_archive_legacy_inventory_migration_drops_recreated_sources_when_archive_exists() -> None:
    migration = importlib.import_module("migrations.standalone.099_archive_legacy_inventory_sources")
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE legacy_inventario_actual (id INTEGER PRIMARY KEY, producto_id INTEGER);
        CREATE TABLE legacy_branch_inventory (id INTEGER PRIMARY KEY, product_id INTEGER);
        CREATE TABLE legacy_movimientos_inventario (id INTEGER PRIMARY KEY, producto_id INTEGER);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id INTEGER);
        CREATE TABLE branch_inventory (id INTEGER PRIMARY KEY, product_id INTEGER);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY, producto_id INTEGER);
        """
    )

    migration.run(conn)

    tables = _tables(conn)
    assert "inventario_actual" not in tables
    assert "branch_inventory" not in tables
    assert "movimientos_inventario" not in tables
    assert "legacy_inventario_actual" in tables
    assert "legacy_branch_inventory" in tables
    assert "legacy_movimientos_inventario" in tables
