import sqlite3

from core.delivery.domain.events import DeliveryEvents
from core.services.delivery_service import DeliveryService, LEGACY_COMPATIBILITY_METHODS
from repositories.delivery_repository import DeliveryRepository


class DummyGeo:
    def geocode(self, _address):
        return None

    def autocomplete(self, _query):
        return []


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

    def pull_orders(self):
        return []


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL)")
    return db, repo


def _service():
    db, repo = _db()
    svc = DeliveryService(db=db, repository=repo, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_args, **_kwargs: None
    return db, svc


def test_delivery_service_exposes_legacy_compatibility_surface():
    _db_conn, svc = _service()

    for name in (
        "create_order",
        "create_delivery_order",
        "update_status",
        "update_order_status",
        "adjust_item_weight",
        "adjust_weight",
        "cancel_order",
        "cancel_delivery_order",
        "list_orders",
        "get_order",
        "get_order_items",
        "pull_orders_from_whatsapp",
        "sync_pending_sales_to_delivery_orders",
    ):
        assert callable(getattr(svc, name))

    assert {
        "_ensure_adjustment_columns",
        "_sync_venta_total",
        "_notify_adjustment_pending",
        "_validate_workflow_transition",
        "_release_stock",
        "sync_pending_sales_to_delivery_orders",
    } <= LEGACY_COMPATIBILITY_METHODS


def test_legacy_aliases_delegate_to_facade_flows_and_record_history():
    db, svc = _service()

    order_id = svc.create_delivery_order({"direccion": "Calle 10", "cliente_tel": "55"}, usuario="tester")
    assert svc.get_order(order_id)["estado"] == "pendiente"

    svc.update_order_status(order_id, "preparacion", usuario="tester", observacion="compat alias")
    db.execute(
        "INSERT INTO delivery_items(delivery_id, nombre, cantidad, precio_unitario, subtotal) VALUES (?, 'Pollo', 1, 100, 100)",
        (order_id,),
    )
    db.commit()
    assert svc.adjust_weight(order_id, 1, 1.1, "op")["applied"] is True

    row = db.execute(
        "SELECT reason, observacion FROM delivery_order_history WHERE order_id=? AND estado_nuevo='preparacion' ORDER BY id DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    assert row["reason"] == "delivery_status_preparacion"
    assert row["observacion"] == "compat alias"


def test_legacy_notification_and_release_shims_prefer_outbox_without_db_payload():
    db, svc = _service()
    order_id = svc.create_order({"direccion": "Calle 20", "cliente_tel": "5512345678"}, usuario="tester")
    order = svc.get_order(order_id)
    svc.whatsapp_service.notifications.clear()

    svc._safe_wa_notify(order, "preparacion")
    svc._release_stock(order_id)

    assert svc.whatsapp_service.notifications == []
    rows = db.execute(
        "SELECT event_type, payload_json FROM delivery_outbox_events WHERE aggregate_id=? ORDER BY id",
        (order_id,),
    ).fetchall()
    event_types = {row["event_type"] for row in rows}
    assert DeliveryEvents.CUSTOMER_NOTIFICATION_REQUESTED.value in event_types
    assert DeliveryEvents.INVENTORY_RELEASE_REQUIRED.value in event_types
    assert all('"db"' not in row["payload_json"] for row in rows)


def test_cancel_delivery_order_alias_preserves_motivo_in_audit_history():
    db, svc = _service()
    order_id = svc.create_order({"direccion": "Calle 30", "cliente_tel": "55"}, usuario="tester")

    result = svc.cancel_delivery_order(order_id, usuario="tester", motivo="cliente pidió cancelar")

    assert result["status"] == "cancelado"
    row = db.execute(
        "SELECT reason, observacion FROM delivery_order_history WHERE order_id=? ORDER BY id DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    assert row["reason"] == "delivery_status_cancelado"
    assert row["observacion"] == "cliente pidió cancelar"
