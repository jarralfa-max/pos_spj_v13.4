import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.delivery.application.adjust_delivery_weight import AdjustDeliveryWeightUseCase
from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from core.delivery.application.create_delivery_order import CreateDeliveryOrderUseCase
from core.delivery.infrastructure.delivery_outbox_repository import DeliveryOutboxRepository
from core.delivery.infrastructure.whatsapp_delivery_notifier import WhatsAppDeliveryNotifier
from core.events.handlers.delivery_handler import DeliveryNotificationDispatchHandler
from notifications.base import NotificationPayload
from notifications.whatsapp_channel import WhatsAppNotificationChannel
from repositories.delivery_repository import DeliveryRepository


class DummyClient:
    def __init__(self):
        self.sent = []

    def enviar_mensaje(self, phone, message):
        self.sent.append((phone, message))
        return True


class DummyGeo:
    def geocode(self, _address):
        return None


class DummyWA:
    def __init__(self):
        self.status = []

    def notify_status(self, **kwargs):
        self.status.append(kwargs)
        return True

    def sync_status(self, *_args, **_kwargs):
        return True


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL)")
    return db, repo


def _seed_preparing_order(db):
    db.execute("INSERT INTO ventas(id, estado, total) VALUES (1, 'en_preparacion', 200)")
    db.execute(
        """
        INSERT INTO delivery_orders(id, venta_id, folio, whatsapp_order_id, cliente_tel, direccion, estado, total, workflow_type)
        VALUES (1, 1, 'DEL-1', 'wa-1', '5512345678', 'Calle 1', 'preparacion', 200, 'delivery')
        """
    )
    db.execute(
        """
        INSERT INTO delivery_items(id, delivery_id, nombre, producto_id, cantidad, precio_unitario, subtotal, final_qty)
        VALUES (1, 1, 'Pollo', 10, 2, 100, 200, 2)
        """
    )
    db.commit()


def test_whatsapp_notifier_templates_status_adjustment_and_event_payloads():
    client = DummyClient()
    notifier = WhatsAppDeliveryNotifier(client)

    assert notifier.notify_status(phone="5512345678", folio="DEL-1", status="en_ruta") is True
    assert "va en ruta" in client.sent[-1][1]

    assert notifier.notify_adjustment_required(
        phone="5512345678",
        folio="DEL-1",
        item_name="Pollo",
        requested_qty=2,
        prepared_qty=2.3,
        unit="kg",
        new_subtotal=230,
    ) is True
    assert "ACEPTAR AJUSTE" in client.sent[-1][1]

    assert notifier.notify_from_event({
        "template": "entregado",
        "cliente_tel": "5512345678",
        "params": {"folio": "DEL-1"},
    }) is True
    assert "entregado" in client.sent[-1][1]


def test_notification_dispatch_handler_routes_whatsapp_to_delivery_notifier():
    calls = []

    class MockNotifier:
        def notify_from_event(self, payload):
            calls.append(payload)
            return True

    handler = DeliveryNotificationDispatchHandler(whatsapp_notifier=MockNotifier())
    handler.handle({"canal": "whatsapp", "template": "en_ruta", "cliente_tel": "55", "params": {"folio": "DEL-1"}})

    assert calls[0]["template"] == "en_ruta"


def test_whatsapp_channel_prefers_notify_from_event_payloads():
    calls = []

    class MockWA:
        def notify_from_event(self, payload):
            calls.append(payload)
            return True

    channel = WhatsAppNotificationChannel(wa_service=MockWA())
    ok = channel.send(NotificationPayload(
        event_type="adjustment_required",
        title="Ajuste",
        body="body",
        channel="whatsapp",
        order_id=1,
        folio="DEL-1",
        cliente_tel="5512345678",
        metadata={"requested_qty": 2, "prepared_qty": 2.4},
    ))

    assert ok is True
    assert calls[0]["template"] == "adjustment_required"
    assert calls[0]["params"]["prepared_qty"] == 2.4


def test_create_and_status_use_cases_only_enqueue_customer_notification_when_outbox_exists():
    db, repo = _db()
    outbox = DeliveryOutboxRepository(db)
    wa = DummyWA()

    order_id = CreateDeliveryOrderUseCase(
        db=db,
        repository=repo,
        geocoding_service=DummyGeo(),
        whatsapp_service=wa,
        outbox_repository=outbox,
    ).execute({"direccion": "Calle 1", "cliente_tel": "5512345678"})

    assert wa.status == []
    assert db.execute("SELECT COUNT(*) FROM delivery_outbox_events WHERE event_type='CUSTOMER_NOTIFICATION_REQUESTED'").fetchone()[0] == 1

    db.execute("UPDATE delivery_orders SET estado='en_ruta' WHERE id=?", (order_id,))
    db.commit()
    ChangeDeliveryStatusUseCase(
        db=db,
        repository=repo,
        whatsapp_service=wa,
        outbox_repository=outbox,
    ).execute(order_id, "entregado", usuario="tester", responsable="r1")

    assert len(wa.status) == 0
    templates = [
        row[0]
        for row in db.execute("SELECT json_extract(payload_json, '$.template') FROM delivery_outbox_events WHERE event_type='CUSTOMER_NOTIFICATION_REQUESTED'")
    ]
    assert "pedido_recibido" in templates
    assert "entregado" in templates


def test_adjustment_pending_enqueues_notification_instead_of_direct_whatsapp_when_outbox_exists():
    db, repo = _db()
    _seed_preparing_order(db)
    outbox = DeliveryOutboxRepository(db)
    direct_notifications = []

    out = AdjustDeliveryWeightUseCase(
        db=db,
        repository=repo,
        outbox_repository=outbox,
        notify_adjustment_pending=lambda *args: direct_notifications.append(args) or True,
        recalculate_order_total=lambda _order_id: 200,
    ).execute(1, 1, 2.25, "op")

    assert out["applied"] is False
    assert direct_notifications == []
    templates = [
        row[0]
        for row in db.execute("SELECT json_extract(payload_json, '$.template') FROM delivery_outbox_events WHERE event_type='CUSTOMER_NOTIFICATION_REQUESTED'")
    ]
    assert templates == ["adjustment_required"]
