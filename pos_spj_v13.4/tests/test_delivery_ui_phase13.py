import sqlite3

from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator
from core.services import delivery_service as delivery_service_module
from core.services.delivery_service import DeliveryService
from integrations.delivery_pwa import pwa_server


class _DummyRepo:
    pass


def test_delivery_service_ui_actions_are_backed_by_state_machine(monkeypatch):
    calls = []

    class FakeStateMachine:
        def get_valid_actions(self, order_context):
            calls.append(order_context)
            return ["en_ruta", "cancelado"]

    monkeypatch.setattr(delivery_service_module, "DeliveryStateMachine", FakeStateMachine)

    svc = DeliveryService(db=None, repository=_DummyRepo(), whatsapp_service=None, geocoding_service=None)
    actions = svc.get_valid_actions(
        status="preparacion",
        workflow_type="delivery",
        adjustment_pending=True,
        scheduled_at="2026-06-03 10:00:00",
        delivery_type="home_delivery",
    )

    assert calls == [{
        "estado": "preparacion",
        "workflow_type": "delivery",
        "delivery_type": "home_delivery",
        "scheduled_at": "2026-06-03 10:00:00",
        "adjustment_pending": True,
    }]
    assert [action["key"] for action in actions] == ["en_ruta", "cancelado"]
    assert actions[0]["label"] == "Enviar a ruta"


def test_pwa_get_pedidos_returns_backend_actions(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    DeliverySchemaMigrator(db).ensure_schema()
    db.execute("CREATE TABLE clientes(id INTEGER PRIMARY KEY, nombre TEXT, telefono TEXT)")
    db.execute("INSERT INTO clientes(id, nombre, telefono) VALUES (1, 'Cliente PWA', '555')")
    db.execute(
        """
        INSERT INTO delivery_orders(
            id, cliente_id, estado, direccion, total, fecha,
            workflow_type, delivery_type, adjustment_pending, driver_id
        ) VALUES (1, 1, 'preparacion', 'Calle PWA', 150, '2026-06-02 10:00:00',
                  'delivery', 'home_delivery', 0, 7)
        """
    )
    db.commit()
    monkeypatch.setattr(pwa_server, "get_connection", lambda: db)

    handler = object.__new__(pwa_server.DeliveryAPIHandler)
    pedidos = handler._get_pedidos("7")

    assert len(pedidos) == 1
    assert pedidos[0]["id"] == "1"
    assert "actions" in pedidos[0]
    assert "en_ruta" in {action["key"] for action in pedidos[0]["actions"]}


def test_pwa_update_status_uses_delivery_service_boundary(monkeypatch):
    calls = []

    class FakeService:
        def __init__(self, conn):
            self.conn = conn

        def update_status(self, order_id, status, usuario, responsable="", observacion=""):
            calls.append({
                "order_id": order_id,
                "status": status,
                "usuario": usuario,
                "responsable": responsable,
                "observacion": observacion,
            })

    monkeypatch.setattr(pwa_server, "get_connection", lambda: object())
    monkeypatch.setattr(pwa_server, "DeliveryService", FakeService)

    handler = object.__new__(pwa_server.DeliveryAPIHandler)
    assert handler._actualizar_estado({"id": "9", "estado": "entregado", "responsable": "driver-7"}) is True

    assert calls == [{
        "order_id": 9,
        "status": "entregado",
        "usuario": "pwa_delivery",
        "responsable": "driver-7",
        "observacion": "",
    }]
