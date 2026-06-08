from __future__ import annotations

import sqlite3

from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE productos("
        "id INTEGER PRIMARY KEY, nombre TEXT, categoria TEXT, existencia REAL, "
        "stock_minimo REAL, unidad TEXT, activo INTEGER)"
    )
    conn.execute(
        "CREATE TABLE inventory_stock("
        "product_id INTEGER, branch_id INTEGER, quantity REAL, unit TEXT, updated_at TEXT, "
        "UNIQUE(product_id, branch_id))"
    )
    conn.execute(
        "CREATE TABLE inventory_movements("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT, product_id INTEGER, "
        "branch_id INTEGER, movement_type TEXT, quantity REAL, stock_before REAL, "
        "stock_after REAL, unit TEXT, source_module TEXT, reference_type TEXT, "
        "reference_id TEXT, reason TEXT, user_name TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO productos VALUES(1,'Pollo','Carnes',4,5,'kg',1)")
    conn.execute("INSERT INTO inventory_stock VALUES(1,2,9,'kg','2026-06-07 09:00')")
    conn.execute(
        """
        INSERT INTO inventory_movements(
            operation_id, product_id, branch_id, movement_type, quantity,
            stock_before, stock_after, unit, source_module, reference_type,
            user_name, created_at
        ) VALUES('OP1',1,2,'ENTRADA',3,6,9,'kg','desktop','ENTRADA','u','2026-06-07 10:00')
        """
    )
    return conn


def test_inventory_query_service_lists_inventory_rows_from_canonical_stock() -> None:
    service = InventoryQueryService(InventoryRepository(_db()))

    rows = service.list_stock_rows(branch_id=2)

    assert rows[0][0] == 1
    assert rows[0][1] == "Pollo"
    assert rows[0][3] == 9


def test_inventory_query_service_returns_kpis_and_history() -> None:
    service = InventoryQueryService(InventoryRepository(_db()))

    assert service.get_last_movement_map(branch_id=2) == {1: "2026-06-07 10:00"}
    assert service.list_product_history(product_id=1, branch_id=2)[0][5] == "OP1"
    assert service.get_operational_kpis(branch_id=2, product_data=[{"health": "BAJO MÍN."}])["stock_bajo"] == 1
