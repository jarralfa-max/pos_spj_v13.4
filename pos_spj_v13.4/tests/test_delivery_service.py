import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.delivery_service import DeliveryService


class DummyGeo:
    def geocode(self, address):
        return {"lat": 19.4, "lng": -99.1, "label": address}

    def autocomplete(self, q):
        return [{"label": "Calle 1", "lat": "19.4", "lng": "-99.1"}]


class DummyWA:
    def __init__(self):
        self.status = []

    def notify_status(self, phone, folio, status):
        self.status.append((phone, folio, status))
        return True

    def pull_orders(self):
        return [{"whatsapp_order_id": "wa-1", "direccion": "Calle 10", "cliente": "Ana"}]

    def sync_status(self, whatsapp_order_id, status):
        return True


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY)")
    return db


def test_create_and_update_delivery_order():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    oid = svc.create_order({
        "cliente_nombre": "Ana",
        "direccion": "Calle Falsa 123",
        "workflow_type": "delivery",
        "delivery_type": "home_delivery",
    }, usuario="tester")
    assert oid > 0

    orders = svc.list_orders()
    assert any(o["id"] == oid for o in orders)

    svc.update_status(oid, "en_ruta", usuario="tester")
    svc.update_status(oid, "entregado", usuario="tester", responsable="carlos")

    order = svc.repository.get_order(oid)
    assert order["estado"] == "entregado"
    assert order["responsable_entrega"] == "carlos"


def test_counter_workflow_cannot_transition_to_en_ruta():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    oid = svc.create_order({
        "cliente_nombre": "Ana",
        "direccion": "Sucursal Centro",
        "workflow_type": "counter",
        "delivery_type": "pickup",
    }, usuario="tester")

    try:
        svc.update_status(oid, "en_ruta", usuario="tester")
        assert False, "Expected ValueError for counter workflow en_ruta transition"
    except ValueError as exc:
        assert "mostrador" in str(exc).lower()


def test_pull_orders_from_whatsapp_upserts():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc.pull_orders_from_whatsapp()
    orders = svc.repository.list_orders()
    assert len(orders) == 1
    assert orders[0]["whatsapp_order_id"] == "wa-1"


def test_activate_scheduled_order_switches_to_counter_when_pickup():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    oid = svc.create_order({
        "cliente_nombre": "Ana",
        "direccion": "Sucursal Centro",
        "workflow_type": "scheduled",
        "delivery_type": "pickup",
    }, usuario="tester")
    svc.repository.update_status(oid, "programado", usuario="tester")

    out = svc.activate_scheduled_order(oid, usuario="tester")
    assert out["workflow_type"] == "counter"
    assert out["status"] == "pending"

    row = svc.repository.get_order(oid)
    assert row["estado"] == "pendiente"
    assert (row.get("workflow_type") or "").lower() == "counter"


def test_activate_scheduled_order_switches_to_delivery_when_home_delivery():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    oid = svc.create_order({
        "cliente_nombre": "Ana",
        "direccion": "Calle Falsa 123",
        "workflow_type": "scheduled",
        "delivery_type": "home_delivery",
    }, usuario="tester")
    svc.repository.update_status(oid, "programado", usuario="tester")

    out = svc.activate_scheduled_order(oid, usuario="tester")
    assert out["workflow_type"] == "delivery"
    assert out["status"] == "pending"

    row = svc.repository.get_order(oid)
    assert row["estado"] == "pendiente"
    assert (row.get("workflow_type") or "").lower() == "delivery"


def test_scheduled_workflow_cannot_jump_to_preparacion_without_activation():
    svc = DeliveryService(_db(), whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    oid = svc.create_order({
        "cliente_nombre": "Ana",
        "direccion": "Sucursal Centro",
        "workflow_type": "scheduled",
        "delivery_type": "pickup",
    }, usuario="tester")
    svc.repository.update_status(oid, "programado", usuario="tester")

    try:
        svc.update_status(oid, "preparacion", usuario="tester")
        assert False, "Expected ValueError for scheduled workflow transition"
    except ValueError as exc:
        assert "programado" in str(exc).lower()
