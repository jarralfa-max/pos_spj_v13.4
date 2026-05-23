import os
import sys
import sqlite3
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'whatsapp_service'))

from core.services.delivery_service import DeliveryService
from repositories.delivery_repository import DeliveryRepository
from erp.adjustment_approval import AdjustmentApprovalService
from core.services.order_total_service import OrderTotalService


class DummyGeo:
    def geocode(self, _a):
        return None


class DummyWA:
    def notify_status(self, **_kwargs):
        return True

    def sync_status(self, *_a, **_k):
        return True

    def pull_orders(self):
        return []


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, total REAL)")
    DeliveryRepository(db)
    try:
        db.execute("ALTER TABLE delivery_orders ADD COLUMN weight_adjusted INTEGER DEFAULT 0")
    except Exception:
        pass
    return db


def _seed_order(db, estado="preparacion"):
    db.execute("INSERT INTO ventas(id,total) VALUES (1,200)")
    db.execute("""
        INSERT INTO delivery_orders(id, venta_id, folio, cliente_tel, direccion, estado, total)
        VALUES (1,1,'DEL-1','5512345678','Calle 1',?,200)
    """, (estado,))
    db.execute("""
        INSERT INTO delivery_items(
            id, delivery_id, nombre, cantidad, precio_unitario, subtotal, unidad,
            prepared_qty, final_qty
        ) VALUES (1,1,'Pollo',2.0,100,200,'kg',2.0,2.0)
    """)
    db.commit()


def _svc(db):
    svc = DeliveryService(db=db, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_a, **_k: None
    svc._notify_adjustment_pending = lambda *_a, **_k: True
    return svc


def test_within_tolerance_updates_total_to_215_and_delivery_keeps_total():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    out = svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.15, prepared_by="op")
    assert out["applied"] is True
    assert out["new_total"] == 215.0

    svc.update_status(1, "entregado", usuario="tester", responsable="r1")
    row = db.execute("SELECT total FROM delivery_orders WHERE id=1").fetchone()
    assert float(row[0]) == 215.0


def test_outside_tolerance_does_not_change_total_until_accept_then_225():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    out = svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.25, prepared_by="op")
    assert out["applied"] is False

    row = db.execute("SELECT total, adjustment_pending FROM delivery_orders WHERE id=1").fetchone()
    assert float(row[0]) == 200.0
    assert int(row[1]) == 1

    with __import__('pytest').raises(ValueError):
        svc.update_status(1, "en_ruta", usuario="tester")

    ap = AdjustmentApprovalService(db)
    resp = ap.respond_latest_for_phone("5512345678", accepted=True)
    assert resp["total"] == 225.0

    svc.update_status(1, "en_ruta", usuario="tester")
    svc.update_status(1, "entregado", usuario="tester", responsable="r1")
    row2 = db.execute("SELECT total FROM delivery_orders WHERE id=1").fetchone()
    assert float(row2[0]) == 225.0


def test_outside_tolerance_reject_keeps_200_and_delivery_keeps_total():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.25, prepared_by="op")
    ap = AdjustmentApprovalService(db)
    resp = ap.respond_latest_for_phone("5512345678", accepted=False)
    assert resp["total"] == 200.0

    svc.update_status(1, "en_ruta", usuario="tester")
    svc.update_status(1, "entregado", usuario="tester", responsable="r1")
    row = db.execute("SELECT total FROM delivery_orders WHERE id=1").fetchone()
    assert float(row[0]) == 200.0


def test_status_transitions_do_not_recalculate_totals_when_no_adjustment_change():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    svc._recalculate_order_total = MagicMock(side_effect=AssertionError("no debe recalcular en entregar/en_ruta"))

    svc.update_status(1, "en_ruta", usuario="tester")
    svc.update_status(1, "entregado", usuario="tester", responsable="r1")

    row = db.execute("SELECT total FROM delivery_orders WHERE id=1").fetchone()
    assert float(row[0]) == 200.0


def test_within_tolerance_recalculates_once_and_delivery_does_not_recalculate_again():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    real_recalc = svc._recalculate_order_total
    svc._recalculate_order_total = MagicMock(side_effect=real_recalc)

    out = svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.1, prepared_by="op")
    assert out["applied"] is True
    assert out["new_total"] == 210.0
    assert svc._recalculate_order_total.call_count == 1

    svc.update_status(1, "en_ruta", usuario="tester")
    svc.update_status(1, "entregado", usuario="tester", responsable="r1")
    assert svc._recalculate_order_total.call_count == 1


def test_pending_adjustment_does_not_recalculate_until_customer_response():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")

    svc._recalculate_order_total = MagicMock(side_effect=AssertionError("pendiente no debe recalcular"))
    out = svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.3, prepared_by="op")
    assert out["applied"] is False

    row = db.execute("SELECT total, adjustment_pending FROM delivery_orders WHERE id=1").fetchone()
    assert float(row[0]) == 200.0
    assert int(row[1]) == 1


def test_adjustment_approval_service_recalculates_exactly_once():
    db = _db(); svc = _svc(db); _seed_order(db, "preparacion")
    svc.adjust_item_weight(order_id=1, item_id=1, prepared_qty=2.3, prepared_by="op")

    original = OrderTotalService.recalculate_order_total
    calls = {"n": 0}

    def _tracked(self, order_id):
        calls["n"] += 1
        return original(self, order_id)

    OrderTotalService.recalculate_order_total = _tracked
    try:
        ap = AdjustmentApprovalService(db)
        out = ap.respond_latest_for_phone("5512345678", accepted=True)
        assert out["ok"] is True
        assert out["total"] == 230.0
        assert calls["n"] == 1
    finally:
        OrderTotalService.recalculate_order_total = original
