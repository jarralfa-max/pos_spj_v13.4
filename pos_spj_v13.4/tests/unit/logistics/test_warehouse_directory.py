import sqlite3

from backend.application.logistics.warehouse_directory import WarehouseDirectoryQueryService


def test_only_active_purchase_receipt_warehouses_are_selectable():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE warehouses (id TEXT, code TEXT, name TEXT, branch_id TEXT,"
        " status TEXT, allow_purchase_receipt INTEGER)")
    connection.executemany("INSERT INTO warehouses VALUES (?,?,?,?,?,?)", [
        ("w1", "ALM", "Principal", "b1", "ACTIVE", 1),
        ("w2", "Q", "Cuarentena", "b1", "ACTIVE", 0),
        ("w3", "OTR", "Otra", "b2", "ACTIVE", 1),
    ])
    assert WarehouseDirectoryQueryService(connection).active_for_branch("b1") == [
        ("w1", "ALM · Principal")]
