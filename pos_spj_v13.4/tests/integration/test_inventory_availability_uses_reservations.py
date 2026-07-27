from __future__ import annotations

import sqlite3

from backend.application.queries.inventory_query_service import InventoryQueryService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from core.services.stock_reservation_service import StockReservationService


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, categoria TEXT, unidad TEXT, stock_minimo REAL, activo INTEGER)")
    conn.execute("CREATE TABLE inventory_stock(product_id INTEGER, branch_id INTEGER, quantity REAL, unit TEXT, PRIMARY KEY(product_id, branch_id))")
    conn.execute("CREATE TABLE inventory_movements(id INTEGER PRIMARY KEY, product_id INTEGER, branch_id INTEGER, created_at TEXT)")
    conn.execute("INSERT INTO productos VALUES(1, 'Pollo', 'Carnes', 'kg', 1, 1)")
    conn.execute("INSERT INTO inventory_stock VALUES(1, 1, 10, 'kg')")
    conn.commit()
    return conn


def test_inventory_availability_uses_active_reservations() -> None:
    conn = _db()
    reservation_service = StockReservationService(conn, branch_id=1)
    reserva_id = reservation_service.reservar("R-INV", [{"id": 1, "cantidad": 2}])
    assert reserva_id > 0

    rows = InventoryQueryService(InventoryRepository(conn)).list_availability_rows(branch_id=1)

    assert rows == [
        {
            "product_id": 1,
            "name": "Pollo",
            "physical_stock": 10.0,
            "reserved": 2.0,
            "physical_available": 8.0,
            "virtual_available": None,
            "sale_available": 8.0,
            "mode": "DIRECTO",
        }
    ]
