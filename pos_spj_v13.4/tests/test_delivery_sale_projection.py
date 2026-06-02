import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "whatsapp_service"))

from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService
from core.services.delivery_service import DeliveryService
from core.services.order_total_service import OrderTotalService
from repositories.delivery_repository import DeliveryRepository


class DummyGeo:
    def geocode(self, _address):
        return None

    def autocomplete(self, _query):
        return []


class DummyWA:
    def notify_status(self, **_kwargs):
        return True

    def sync_status(self, *_args, **_kwargs):
        return True

    def pull_orders(self):
        return []


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL, workflow_type TEXT)")
    db.execute("INSERT INTO ventas(id, estado, total, workflow_type) VALUES (1, 'pendiente', 100, NULL)")
    db.execute(
        """
        INSERT INTO delivery_orders(id, venta_id, folio, direccion, estado, total, delivery_type)
        VALUES (1, 1, 'DEL-1', 'Calle 1', 'pendiente', 100, 'domicilio')
        """
    )
    db.execute(
        """
        INSERT INTO delivery_items(delivery_id, nombre, cantidad, precio_unitario, subtotal)
        VALUES (1, 'Pollo', 2, 60, 120)
        """
    )
    db.commit()
    return db


def test_projection_maps_delivery_status_to_sale_status():
    db = _db()
    projection = SaleDeliveryProjectionService(db)

    assert projection.project_status(1, "preparacion") is True

    row = db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()
    assert row["estado"] == "en_preparacion"


def test_repository_update_status_does_not_update_ventas_directly():
    db = _db()
    repo = DeliveryRepository(db)

    repo.update_status(1, "en_ruta", usuario="tester")

    venta = db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()
    delivery = db.execute("SELECT estado FROM delivery_orders WHERE id=1").fetchone()
    assert delivery["estado"] == "en_ruta"
    assert venta["estado"] == "pendiente"


def test_delivery_service_update_status_projects_to_ventas_once():
    db = _db()
    svc = DeliveryService(db=db, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_args, **_kwargs: None

    svc.update_status(1, "preparacion", usuario="tester")

    venta = db.execute("SELECT estado FROM ventas WHERE id=1").fetchone()
    assert venta["estado"] == "en_preparacion"


def test_order_total_service_only_updates_delivery_total():
    db = _db()

    total = OrderTotalService(db).recalculate_order_total(1)

    delivery = db.execute("SELECT total FROM delivery_orders WHERE id=1").fetchone()
    venta = db.execute("SELECT total FROM ventas WHERE id=1").fetchone()
    assert total == 120.0
    assert delivery["total"] == 120.0
    assert venta["total"] == 100.0


def test_delivery_service_sync_venta_total_uses_projection():
    db = _db()
    svc = DeliveryService(db=db, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())

    svc._sync_venta_total(1, 130.0)

    venta = db.execute("SELECT total FROM ventas WHERE id=1").fetchone()
    assert venta["total"] == 130.0


def test_scheduled_activation_projects_workflow_and_sale_status():
    db = _db()
    db.execute("UPDATE delivery_orders SET estado='programado', delivery_type='pickup' WHERE id=1")
    db.commit()
    svc = DeliveryService(db=db, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_args, **_kwargs: None

    out = svc.activate_scheduled_order(1, usuario="tester")

    venta = db.execute("SELECT estado, workflow_type FROM ventas WHERE id=1").fetchone()
    assert out["workflow_type"] == "counter"
    assert venta["estado"] == "pendiente"
    assert venta["workflow_type"] == "counter"


def test_projection_is_safe_when_ventas_columns_are_absent():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY)")

    projection = SaleDeliveryProjectionService(db)

    assert projection.project_status(1, "entregado") is False
    assert projection.project_total(1, 99.0) is False


def test_adjustment_approval_projects_accepted_total_to_sale():
    from erp.adjustment_approval import AdjustmentApprovalService

    db = _db()
    db.execute(
        """
        UPDATE delivery_items
        SET adjustment_status='pending_customer', pending_prepared_qty=2.5, pending_subtotal=150
        WHERE delivery_id=1
        """
    )
    db.execute("UPDATE delivery_orders SET cliente_tel='5512345678', adjustment_pending=1 WHERE id=1")
    db.commit()

    out = AdjustmentApprovalService(db).respond_latest_for_phone("5512345678", accepted=True)

    venta = db.execute("SELECT total FROM ventas WHERE id=1").fetchone()
    assert out["total"] == 150.0
    assert venta["total"] == 150.0
