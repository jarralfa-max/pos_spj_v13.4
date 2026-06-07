from __future__ import annotations

import sqlite3

from backend.application.queries.inventory_query_service import InventoryQueryService


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE productos("
        "id INTEGER PRIMARY KEY, nombre TEXT, categoria TEXT, existencia REAL, "
        "stock_minimo REAL, unidad TEXT, activo INTEGER)"
    )
    conn.execute("CREATE TABLE branch_inventory(product_id INTEGER, branch_id INTEGER, quantity REAL)")
    conn.execute(
        "CREATE TABLE inventory_movements("
        "product_id INTEGER, branch_id INTEGER, created_at TEXT, movement_type TEXT, "
        "quantity REAL, usuario TEXT, reference_type TEXT, operation_id TEXT, reference TEXT, origin TEXT)"
    )
    conn.execute("INSERT INTO productos VALUES(1,'Pollo','Carnes',4,5,'kg',1)")
    conn.execute("INSERT INTO branch_inventory VALUES(1,2,9)")
    conn.execute(
        "INSERT INTO inventory_movements VALUES(1,2,'2026-06-07 10:00','ENTRADA',3,'u','ENTRADA','OP1','ref','desktop')"
    )
    return conn


def test_inventory_query_service_lists_inventory_rows_without_ui_sql() -> None:
    service = InventoryQueryService(_db())

    rows = service.list_inventory_rows(branch_id=2)

    assert rows[0][0] == 1
    assert rows[0][1] == "Pollo"
    assert rows[0][3] == 9


def test_inventory_query_service_returns_kpis_and_history() -> None:
    service = InventoryQueryService(_db())

    assert service.get_last_movement_by_product(branch_id=2) == {1: "2026-06-07 10:00"}
    assert service.list_product_history(product_id=1, branch_id=2)[0][5] == "OP1"
    assert service.get_operational_kpis(branch_id=2, product_data=[{"health": "BAJO MÍN."}])["stock_bajo"] == 1
