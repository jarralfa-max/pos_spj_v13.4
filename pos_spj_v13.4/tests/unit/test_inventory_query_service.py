from __future__ import annotations

import sqlite3
import uuid

from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository

# Identidad UUIDv7 (REGLA CERO): productos y sucursales son UUID strings.
PROD = str(uuid.uuid4())
BR = str(uuid.uuid4())


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE productos("
        "id TEXT PRIMARY KEY, nombre TEXT, categoria TEXT, existencia REAL, "
        "stock_minimo REAL, unidad TEXT, activo INTEGER)"
    )
    conn.execute(
        "CREATE TABLE inventory_stock("
        "product_id TEXT, branch_id TEXT, quantity REAL, unit TEXT, updated_at TEXT, "
        "PRIMARY KEY(product_id, branch_id))"
    )
    conn.execute(
        "CREATE TABLE inventory_movements("
        "id TEXT PRIMARY KEY, operation_id TEXT, product_id TEXT, "
        "branch_id TEXT, movement_type TEXT, quantity REAL, stock_before REAL, "
        "stock_after REAL, unit TEXT, source_module TEXT, reference_type TEXT, "
        "reference_id TEXT, reason TEXT, user_name TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO productos VALUES(?,'Pollo','Carnes',4,5,'kg',1)", (PROD,))
    conn.execute("INSERT INTO inventory_stock VALUES(?,?,9,'kg','2026-06-07 09:00')", (PROD, BR))
    conn.execute(
        """
        INSERT INTO inventory_movements(
            id, operation_id, product_id, branch_id, movement_type, quantity,
            stock_before, stock_after, unit, source_module, reference_type,
            user_name, created_at
        ) VALUES(?,'OP1',?,?,'ENTRADA',3,6,9,'kg','desktop','ENTRADA','u','2026-06-07 10:00')
        """,
        (str(uuid.uuid4()), PROD, BR),
    )
    return conn


def test_inventory_query_service_lists_inventory_rows_from_canonical_stock() -> None:
    service = InventoryQueryService(InventoryRepository(_db()))

    rows = service.list_stock_rows(branch_id=BR)

    assert rows[0][0] == PROD
    assert rows[0][1] == "Pollo"
    assert rows[0][3] == 9


def test_inventory_query_service_returns_kpis_and_history() -> None:
    service = InventoryQueryService(InventoryRepository(_db()))

    assert service.get_last_movement_map(branch_id=BR) == {PROD: "2026-06-07 10:00"}
    assert service.list_product_history(product_id=PROD, branch_id=BR)[0][5] == "OP1"
    assert service.get_operational_kpis(branch_id=BR, product_data=[{"health": "BAJO MÍN."}])["stock_bajo"] == 1
