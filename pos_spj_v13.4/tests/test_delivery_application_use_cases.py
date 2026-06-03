import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.delivery.application.activate_scheduled_order import ActivateScheduledOrderUseCase
from core.delivery.application.adjust_delivery_weight import AdjustDeliveryWeightUseCase
from core.delivery.application.cancel_delivery_order import CancelDeliveryOrderUseCase
from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from core.delivery.application.create_delivery_order import CreateDeliveryOrderUseCase
from core.delivery.application.sync_whatsapp_orders import SyncWhatsAppOrdersUseCase
from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService
from core.services.delivery_service import DeliveryService
from core.services.order_total_service import OrderTotalService
from repositories.delivery_repository import DeliveryRepository


class DummyGeo:
    def __init__(self):
        self.calls = []

    def geocode(self, address):
        self.calls.append(address)
        return {"lat": 19.43, "lng": -99.13}

    def autocomplete(self, _query):
        return []


class DummyWA:
    def __init__(self, pulled=None):
        self.pulled = pulled or []
        self.notifications = []
        self.synced = []

    def notify_status(self, **kwargs):
        self.notifications.append(kwargs)
        return True

    def sync_status(self, whatsapp_order_id, status):
        self.synced.append((whatsapp_order_id, status))
        return True

    def pull_orders(self):
        return list(self.pulled)


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL, workflow_type TEXT, canal TEXT, direccion TEXT)")
    db.execute(
        """
        CREATE TABLE detalles_venta(
            id INTEGER PRIMARY KEY,
            venta_id INTEGER,
            producto_id INTEGER,
            producto_nombre TEXT,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL
        )
        """
    )
    return db, repo


def _events():
    published = []

    def publish(event, payload):
        published.append((event, payload))

    return published, publish


def _seed_order(db, repo, *, estado="pendiente", venta_id=1, workflow_type="delivery", delivery_type="domicilio"):
    db.execute(
        "INSERT INTO ventas(id, estado, total, workflow_type, canal, direccion) VALUES (?, 'pendiente', 200, NULL, 'whatsapp', 'Calle 1')",
        (venta_id,),
    )
    db.execute(
        """
        INSERT INTO delivery_orders(id, venta_id, folio, whatsapp_order_id, cliente_tel, direccion, estado, total, workflow_type, delivery_type)
        VALUES (1, ?, 'DEL-1', 'wa-1', '5512345678', 'Calle 1', ?, 200, ?, ?)
        """,
        (venta_id, estado, workflow_type, delivery_type),
    )
    db.execute(
        """
        INSERT INTO delivery_items(id, delivery_id, nombre, cantidad, precio_unitario, subtotal, unidad, prepared_qty, final_qty)
        VALUES (1, 1, 'Pollo', 2.0, 100, 200, 'kg', 2.0, 2.0)
        """
    )
    db.commit()


def test_create_delivery_order_use_case_validates_geocodes_persists_and_publishes_without_db_payload():
    db, repo = _db()
    geo = DummyGeo()
    wa = DummyWA()
    published, publish = _events()

    order_id = CreateDeliveryOrderUseCase(
        db=db,
        repository=repo,
        geocoding_service=geo,
        whatsapp_service=wa,
        publisher=publish,
    ).execute(
        {
            "folio": "DEL-X",
            "cliente_tel": "5512345678",
            "direccion": "Calle 123",
            "items": [{"producto_id": 10, "nombre": "Pollo", "cantidad": 2, "precio_unitario": 50}],
        },
        usuario="tester",
    )

    row = repo.get_order(order_id)
    assert row["lat"] == 19.43
    assert geo.calls == ["Calle 123"]
    assert wa.notifications[0]["status"] == "pedido_recibido"
    assert {event for event, _payload in published} >= {"DELIVERY_ORDER_CREATED", "DELIVERY_ORDER_RESERVED"}
    assert "pedido_delivery_creado" not in {event for event, _payload in published}
    assert all("db" not in payload for _event, payload in published)


def test_create_delivery_order_use_case_requires_address():
    db, repo = _db()
    with pytest.raises(ValueError, match="dirección"):
        CreateDeliveryOrderUseCase(db=db, repository=repo).execute({"direccion": "  "})


def test_change_status_use_case_projects_sale_and_emits_inventory_commit_without_db_payload():
    db, repo = _db()
    _seed_order(db, repo, estado="en_ruta")
    published, publish = _events()
    wa = DummyWA()

    ChangeDeliveryStatusUseCase(
        db=db,
        repository=repo,
        sale_projection=SaleDeliveryProjectionService(db),
        whatsapp_service=wa,
        publisher=publish,
        get_order_items=lambda _order_id: [{"producto_id": 10, "final_qty": 2.0}],
    ).execute(1, "entregado", usuario="tester", responsable="r1")

    assert db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()["estado"] == "entregada"
    assert any(event == "DELIVERY_ORDER_DELIVERED" for event, _payload in published)
    assert all(event != "pedido_entregado" for event, _payload in published)
    commit_payload = [payload for event, payload in published if event == "INVENTORY_COMMIT_REQUIRED"][0]
    assert commit_payload["operation_id"] == "delivery:1"
    assert "db" not in commit_payload
    assert wa.synced == [("wa-1", "entregado")]


def test_change_status_use_case_blocks_pending_adjustments_before_route():
    db, repo = _db()
    _seed_order(db, repo, estado="preparacion")
    db.execute("UPDATE delivery_items SET adjustment_status='pending_customer' WHERE id=1")
    db.commit()

    with pytest.raises(ValueError, match="ajuste"):
        ChangeDeliveryStatusUseCase(db=db, repository=repo).execute(1, "en_ruta", usuario="tester")

    row = db.execute("SELECT adjustment_pending, adjustment_blocked_state FROM delivery_orders WHERE id=1").fetchone()
    assert int(row["adjustment_pending"]) == 1
    assert row["adjustment_blocked_state"] == "en_ruta"


def test_adjust_weight_use_case_applies_tolerance_and_projects_total_callback_without_db_payload():
    db, repo = _db()
    _seed_order(db, repo, estado="preparacion")
    published, publish = _events()
    projected = []

    out = AdjustDeliveryWeightUseCase(
        db=db,
        repository=repo,
        publisher=publish,
        recalculate_order_total=OrderTotalService(db).recalculate_order_total,
        sync_sale_total=lambda order_id, total: projected.append((order_id, total)),
    ).execute(1, 1, 2.1, "op")

    assert out["applied"] is True
    assert out["new_total"] == 210.0
    assert projected == [(1, 210.0)]
    assert all("db" not in payload for _event, payload in published)


def test_adjust_weight_use_case_marks_customer_pending_outside_tolerance():
    db, repo = _db()
    _seed_order(db, repo, estado="preparacion")
    notifications = []

    out = AdjustDeliveryWeightUseCase(
        db=db,
        repository=repo,
        notify_adjustment_pending=lambda *args: notifications.append(args) or True,
        recalculate_order_total=OrderTotalService(db).recalculate_order_total,
    ).execute(1, 1, 2.25, "op")

    item = db.execute("SELECT adjustment_status, pending_prepared_qty FROM delivery_items WHERE id=1").fetchone()
    assert out["applied"] is False
    assert item["adjustment_status"] == "pending_customer"
    assert item["pending_prepared_qty"] == 2.25
    assert notifications


def test_activate_scheduled_order_use_case_moves_to_operational_workflow_and_projects_sale():
    db, repo = _db()
    _seed_order(db, repo, estado="programado", workflow_type="scheduled", delivery_type="pickup")
    published, publish = _events()

    result = ActivateScheduledOrderUseCase(
        db=db,
        repository=repo,
        sale_projection=SaleDeliveryProjectionService(db),
        publisher=publish,
    ).execute(1, usuario="tester")

    order = repo.get_order(1)
    sale = db.execute("SELECT estado, workflow_type FROM ventas WHERE id=1").fetchone()
    assert result == {"order_id": 1, "workflow_type": "counter", "status": "pending"}
    assert order["estado"] == "pendiente"
    assert sale["workflow_type"] == "counter"
    assert all("db" not in payload for _event, payload in published)


def test_cancel_delivery_order_use_case_wraps_status_change():
    db, repo = _db()
    _seed_order(db, repo, estado="preparacion")
    change_status = ChangeDeliveryStatusUseCase(
        db=db,
        repository=repo,
        sale_projection=SaleDeliveryProjectionService(db),
    )

    result = CancelDeliveryOrderUseCase(change_status).execute(1, usuario="tester", motivo="cliente")

    assert result["status"] == "cancelado"
    assert repo.get_order(1)["estado"] == "cancelado"
    assert db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()["estado"] == "cancelada"


def test_sync_whatsapp_orders_use_case_upserts_pulled_orders_and_falls_back_to_local_sales():
    db, repo = _db()
    wa = DummyWA([
        {"whatsapp_order_id": "wa-2", "folio": "WA-2", "cliente_tel": "55", "direccion": "Calle WA", "total": 99}
    ])
    published, publish = _events()

    SyncWhatsAppOrdersUseCase(db=db, repository=repo, whatsapp_service=wa, publisher=publish).pull_orders_from_whatsapp()

    assert db.execute("SELECT COUNT(*) FROM delivery_orders WHERE whatsapp_order_id='wa-2'").fetchone()[0] == 1
    assert any(event == "DELIVERY_ORDER_CREATED" for event, _payload in published)
    assert all(event != "pedido_whatsapp_recibido" for event, _payload in published)

    db.execute("INSERT INTO ventas(id, estado, total, canal, direccion) VALUES (2, 'pendiente_wa', 50, 'whatsapp', 'Calle local')")
    db.commit()
    imported = SyncWhatsAppOrdersUseCase(db=db, repository=repo, whatsapp_service=DummyWA()).sync_pending_sales_to_delivery_orders()

    assert imported == 1
    assert db.execute("SELECT COUNT(*) FROM delivery_orders WHERE venta_id=2").fetchone()[0] == 1


def test_delivery_service_is_application_facade_for_core_methods():
    db, repo = _db()
    geo = DummyGeo()
    wa = DummyWA()
    svc = DeliveryService(db=db, repository=repo, whatsapp_service=wa, geocoding_service=geo)
    svc._publish = lambda *_args, **_kwargs: None

    order_id = svc.create_order({"direccion": "Calle 123", "cliente_tel": "55"}, usuario="tester")
    db.execute("UPDATE delivery_orders SET estado='preparacion' WHERE id=?", (order_id,))
    db.execute(
        """
        INSERT INTO delivery_items(delivery_id, nombre, cantidad, precio_unitario, subtotal)
        VALUES (?, 'Pollo', 1, 100, 100)
        """,
        (order_id,),
    )
    db.commit()

    assert svc.adjust_item_weight(order_id, 1, 1.1, "op")["applied"] is True
    svc.update_status(order_id, "en_ruta", usuario="tester")
    svc.update_status(order_id, "entregado", usuario="tester", responsable="r1")
    assert svc.list_orders()[0]["estado"] == "entregado"
