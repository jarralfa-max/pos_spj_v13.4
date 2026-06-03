import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from core.delivery.application.create_delivery_order import CreateDeliveryOrderUseCase
from core.delivery.application.process_delivery_outbox import ProcessDeliveryOutboxUseCase
from core.delivery.infrastructure.delivery_outbox_repository import DeliveryOutboxRepository
from repositories.delivery_repository import DeliveryRepository


class DummyWA:
    def __init__(self):
        self.notifications = []
        self.synced = []

    def notify_status(self, **kwargs):
        self.notifications.append(kwargs)
        return True

    def sync_status(self, whatsapp_order_id, status):
        self.synced.append((whatsapp_order_id, status))
        return True


class DummyGeo:
    def geocode(self, _address):
        return None


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL)")
    return db, repo


def _seed_delivery_in_route(db):
    db.execute("INSERT INTO ventas(id, estado, total) VALUES (1, 'en_ruta', 200)")
    db.execute(
        """
        INSERT INTO delivery_orders(id, venta_id, folio, whatsapp_order_id, cliente_tel, direccion, estado, total, workflow_type)
        VALUES (1, 1, 'DEL-1', 'wa-1', '5512345678', 'Calle 1', 'en_ruta', 200, 'delivery')
        """
    )
    db.execute(
        """
        INSERT INTO delivery_items(id, delivery_id, nombre, producto_id, cantidad, precio_unitario, subtotal, final_qty)
        VALUES (1, 1, 'Pollo', 10, 2, 100, 200, 2)
        """
    )
    db.commit()


def test_outbox_repository_is_idempotent_by_operation_id_and_strips_db_payload():
    db, _repo = _db()
    outbox = DeliveryOutboxRepository(db)

    first = outbox.enqueue(
        event_type="INVENTORY_COMMIT_REQUIRED",
        aggregate_id=1,
        payload={"order_id": 1, "operation_id": "delivery:1", "db": db},
        operation_id="delivery:1",
        commit=True,
    )
    second = outbox.enqueue(
        event_type="INVENTORY_COMMIT_REQUIRED",
        aggregate_id=1,
        payload={"order_id": 1, "operation_id": "delivery:1", "db": db},
        operation_id="delivery:1",
        commit=True,
    )

    assert first == second
    assert db.execute("SELECT COUNT(*) FROM delivery_outbox_events").fetchone()[0] == 1
    payload = outbox.payload_for(first)
    assert payload == {"order_id": 1, "operation_id": "delivery:1"}


def test_create_order_use_case_enqueues_outbox_events_in_committed_transaction_without_db_payload():
    db, repo = _db()
    outbox = DeliveryOutboxRepository(db)
    published = []

    order_id = CreateDeliveryOrderUseCase(
        db=db,
        repository=repo,
        geocoding_service=DummyGeo(),
        whatsapp_service=DummyWA(),
        publisher=lambda event, payload: published.append((event, payload)),
        outbox_repository=outbox,
    ).execute(
        {
            "direccion": "Calle 1",
            "cliente_tel": "55",
            "items": [{"producto_id": 10, "nombre": "Pollo", "cantidad": 2, "precio_unitario": 100}],
        },
        usuario="tester",
    )

    rows = db.execute("SELECT event_type, payload_json FROM delivery_outbox_events WHERE aggregate_id=?", (order_id,)).fetchall()
    event_types = {row["event_type"] for row in rows}
    assert "DELIVERY_ORDER_RESERVED" in event_types
    assert "CUSTOMER_NOTIFICATION_REQUESTED" in event_types
    assert all('"db"' not in row["payload_json"] for row in rows)
    assert repo.get_order(order_id)["direccion"] == "Calle 1"


def test_delivered_status_enqueues_critical_outbox_events_and_projects_sale():
    db, repo = _db()
    _seed_delivery_in_route(db)
    outbox = DeliveryOutboxRepository(db)

    ChangeDeliveryStatusUseCase(
        db=db,
        repository=repo,
        outbox_repository=outbox,
        whatsapp_service=DummyWA(),
        get_order_items=lambda _order_id: [{"producto_id": 10, "final_qty": 2}],
        sale_projection=__import__(
            "core.delivery.projections.sale_delivery_projection",
            fromlist=["SaleDeliveryProjectionService"],
        ).SaleDeliveryProjectionService(db),
    ).execute(1, "entregado", usuario="tester", responsable="r1")

    event_types = {
        row[0]
        for row in db.execute("SELECT event_type FROM delivery_outbox_events WHERE aggregate_id=1").fetchall()
    }
    assert {"DELIVERY_ORDER_DELIVERED", "INVENTORY_COMMIT_REQUIRED", "CUSTOMER_NOTIFICATION_REQUESTED"} <= event_types
    assert db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()[0] == "entregada"


def test_process_delivery_outbox_marks_done_and_records_retry_errors():
    db, _repo = _db()
    outbox = DeliveryOutboxRepository(db)
    ok_id = outbox.enqueue(event_type="OK", aggregate_id=1, payload={"order_id": 1}, commit=True)
    fail_id = outbox.enqueue(event_type="FAIL", aggregate_id=1, payload={"order_id": 1}, commit=True)
    handled = []

    result = ProcessDeliveryOutboxUseCase(
        outbox_repository=outbox,
        handlers={
            "OK": lambda payload: handled.append(payload["order_id"]),
            "FAIL": lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
        },
    ).execute(limit=10)

    ok = db.execute("SELECT status, processed_at FROM delivery_outbox_events WHERE id=?", (ok_id,)).fetchone()
    fail = db.execute("SELECT status, retries, last_error FROM delivery_outbox_events WHERE id=?", (fail_id,)).fetchone()
    assert result == {"processed": 1, "failed": 1}
    assert handled == [1]
    assert ok["status"] == "done"
    assert ok["processed_at"] is not None
    assert fail["status"] == "pending"
    assert fail["retries"] == 1
    assert "boom" in fail["last_error"]
