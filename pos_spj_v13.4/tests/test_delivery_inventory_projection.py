import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.delivery.application.process_delivery_outbox import ProcessDeliveryOutboxUseCase
from core.delivery.infrastructure.delivery_outbox_repository import DeliveryOutboxRepository
from core.delivery.infrastructure.inventory_reservation_adapter import ReservationServiceInventoryAdapter
from core.delivery.projections.delivery_inventory_projection import DeliveryInventoryProjectionService
from repositories.delivery_repository import DeliveryRepository


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    DeliveryRepository(db)
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL DEFAULT 0, precio_compra REAL DEFAULT 0)")
    db.execute(
        """
        CREATE TABLE inventario_actual(
            producto_id INTEGER,
            sucursal_id INTEGER,
            cantidad REAL,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT,
            PRIMARY KEY(producto_id, sucursal_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE branch_inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            branch_id INTEGER,
            quantity REAL,
            batch_id INTEGER,
            updated_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE movimientos_inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            producto_id INTEGER,
            sucursal_id INTEGER,
            tipo_movimiento TEXT,
            referencia_tipo TEXT,
            referencia_id TEXT,
            cantidad REAL,
            costo_unitario REAL,
            operation_id TEXT,
            usuario TEXT,
            nota TEXT
        )
        """
    )
    db.execute("INSERT INTO productos(id, nombre, existencia, precio_compra) VALUES (10, 'Pollo', 10, 20)")
    db.execute("INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad, costo_promedio) VALUES (10, 1, 10, 20)")
    db.commit()
    return db


def test_inventory_projection_reserves_releases_and_is_idempotent():
    db = _db()
    projection = DeliveryInventoryProjectionService(ReservationServiceInventoryAdapter(db))
    payload = {
        "order_id": 1,
        "operation_id": "delivery:1",
        "items": [{"producto_id": 10, "cantidad": 2}],
        "branch_id": 1,
    }

    first = projection.handle_order_reserved(payload)
    second = projection.handle_order_reserved(payload)

    assert first["reserved"] == 1
    assert second["reserved"] == 0
    assert db.execute("SELECT COUNT(*) FROM inventory_reservations WHERE operation_id='delivery:1'").fetchone()[0] == 1

    released = projection.handle_inventory_release_required({"order_id": 1, "operation_id": "delivery:1", "reason": "cancelado"})
    assert released["released"] == 1
    assert db.execute("SELECT released FROM inventory_reservations WHERE operation_id='delivery:1'").fetchone()[0] == 1


def test_inventory_projection_commit_uses_final_qty_and_item_operation_id_idempotency():
    db = _db()
    projection = DeliveryInventoryProjectionService(ReservationServiceInventoryAdapter(db))
    projection.handle_order_reserved({
        "order_id": 2,
        "operation_id": "delivery:2",
        "items": [{"id": 7, "producto_id": 10, "cantidad": 3}],
        "branch_id": 1,
    })

    payload = {
        "order_id": 2,
        "operation_id": "delivery:2",
        "items": [{"id": 7, "producto_id": 10, "cantidad": 3, "prepared_qty": 2.5, "final_qty": 2.25}],
        "branch_id": 1,
    }
    first = projection.handle_inventory_commit_required(payload)
    second = projection.handle_inventory_commit_required(payload)

    stock = db.execute("SELECT cantidad FROM inventario_actual WHERE producto_id=10 AND sucursal_id=1").fetchone()[0]
    movement = db.execute("SELECT cantidad, operation_id FROM movimientos_inventario WHERE producto_id=10").fetchone()
    assert first["committed"] == 1
    assert second["committed"] == 0
    assert stock == 7.75
    assert movement["cantidad"] == -2.25
    assert movement["operation_id"] == "delivery:2:item:7:commit"


def test_outbox_processor_can_route_inventory_handlers():
    db = _db()
    outbox = DeliveryOutboxRepository(db)
    projection = DeliveryInventoryProjectionService(ReservationServiceInventoryAdapter(db))
    outbox.enqueue(
        event_type="DELIVERY_ORDER_RESERVED",
        aggregate_id=3,
        payload={"order_id": 3, "operation_id": "delivery:3", "items": [{"producto_id": 10, "cantidad": 1}], "branch_id": 1},
        operation_id="delivery:3",
        commit=True,
    )

    result = ProcessDeliveryOutboxUseCase(outbox_repository=outbox, handlers=projection.handlers()).execute()

    assert result == {"processed": 1, "failed": 0}
    assert db.execute("SELECT reserved_qty FROM inventory_reservations WHERE operation_id='delivery:3'").fetchone()[0] == 1
    assert db.execute("SELECT status FROM delivery_outbox_events").fetchone()[0] == "done"
