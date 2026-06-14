from __future__ import annotations

import sqlite3

from backend.application.services.inventory_application_service import InventoryApplicationService
from backend.infrastructure.db.repositories.inventory_repository import InventoryRepository
from core.events.handlers.inventory_handler import SaleInventoryHandler


class EventBusSpy:
    def __init__(self):
        self.events = []

    def publish(self, event, *args, **kwargs):
        self.events.append(event)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE inventory_stock (product_id INTEGER, branch_id INTEGER, quantity REAL, unit TEXT, updated_at TEXT, PRIMARY KEY(product_id, branch_id))")
    conn.execute("""
        CREATE TABLE inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT,
            product_id INTEGER,
            branch_id INTEGER,
            movement_type TEXT,
            quantity REAL,
            stock_before REAL,
            stock_after REAL,
            unit TEXT,
            source_module TEXT,
            reference_type TEXT,
            reference_id TEXT,
            reason TEXT,
            user_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO inventory_stock(product_id, branch_id, quantity, unit) VALUES (1, 1, 10, 'unit')")
    conn.commit()
    return conn


def test_inventory_deduction_rolls_back_when_later_sale_step_fails() -> None:
    conn = _db()
    bus = EventBusSpy()
    service = InventoryApplicationService(repository=InventoryRepository(conn), event_bus=bus)
    handler = SaleInventoryHandler(service)

    conn.execute("SAVEPOINT sale_sp")
    handler.handle({
        "branch_id": 1,
        "operation_id": "sale-op",
        "sale_id": "200",
        "user": "ana",
        "items": [{"product_id": 1, "qty": 4, "es_compuesto": 0}],
    })
    assert conn.execute("SELECT quantity FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone()[0] == 6
    assert bus.events == []

    conn.execute("ROLLBACK TO SAVEPOINT sale_sp")
    conn.execute("RELEASE SAVEPOINT sale_sp")

    assert conn.execute("SELECT quantity FROM inventory_stock WHERE product_id=1 AND branch_id=1").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0
