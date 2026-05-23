import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.desktop_notification_service import DesktopNotificationService


class DummySound:
    def __init__(self):
        self.played = []

    def play_for_notification(self, dedupe_key: str, severity: str = "info"):
        self.played.append((dedupe_key, severity))
        return True


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


def test_create_notification_is_idempotent_and_plays_sound_once():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_new_order(branch_id=1, sale_id=10, folio="WA-10", total=100)
    ok2 = svc.notify_new_order(branch_id=1, sale_id=10, folio="WA-10", total=100)

    assert ok1 is True
    assert ok2 is False
    n = db.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0]
    assert n == 1
    assert snd.played == [("new_order:10", "info")]


def test_scheduled_notification_uses_warning_and_branch_scope():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    svc.notify_scheduled_order(branch_id=2, sale_id=11, folio="WA-11", scheduled_at="2026-06-10 09:00:00")
    row = db.execute("SELECT sucursal_id, severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()

    assert int(row["sucursal_id"]) == 2
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "scheduled_order:11"
    assert row["titulo"] == "Pedido programado"


def test_get_unread_and_mark_as_read():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    svc.notify_new_order(branch_id=1, sale_id=20, folio="WA-20", total=200)
    svc.notify_scheduled_order(branch_id=1, sale_id=21, folio="WA-21", scheduled_at="2026-06-12 12:00:00")

    unread = svc.get_unread_notifications(branch_id=1)
    assert len(unread) == 2
    first_id = unread[0]["id"]

    svc.mark_as_read(notification_id=first_id)
    unread2 = svc.get_unread_notifications(branch_id=1)
    assert len(unread2) == 1


def test_get_unread_notifications_are_branch_scoped():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    svc.notify_new_order(branch_id=1, sale_id=31, folio="WA-31", total=310)
    svc.notify_new_order(branch_id=2, sale_id=32, folio="WA-32", total=320)

    b1 = svc.get_unread_notifications(branch_id=1)
    b2 = svc.get_unread_notifications(branch_id=2)
    assert len(b1) == 1
    assert len(b2) == 1
    assert b1[0]["dedupe_key"] == "new_order:31"
    assert b2[0]["dedupe_key"] == "new_order:32"


def test_quote_converted_notification_uses_success_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_quote_converted(branch_id=3, quote_id=15, sale_id=30, folio="VTA-30", total=330)
    ok2 = svc.notify_quote_converted(branch_id=3, quote_id=15, sale_id=30, folio="VTA-30", total=330)

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT sucursal_id, severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert int(row["sucursal_id"]) == 3
    assert row["severity"] == "success"
    assert row["dedupe_key"] == "quote_converted:15:30"
    assert row["titulo"] == "Cotización aceptada"


def test_order_cancelled_notification_uses_critical_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_order_cancelled(branch_id=4, sale_id=77, folio="VTA-77", reason="Cliente lo canceló")
    ok2 = svc.notify_order_cancelled(branch_id=4, sale_id=77, folio="VTA-77", reason="Cliente lo canceló")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT sucursal_id, severity, dedupe_key, titulo, cuerpo FROM notification_inbox LIMIT 1").fetchone()
    assert int(row["sucursal_id"]) == 4
    assert row["severity"] == "critical"
    assert row["dedupe_key"] == "order_cancelled:77"
    assert row["titulo"] == "Pedido cancelado"
    assert "Cliente lo canceló" in row["cuerpo"]


def test_adjustment_required_notification_uses_warning_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_adjustment_required(branch_id=5, delivery_order_id=22, item_id=9, folio="DEL-22")
    ok2 = svc.notify_adjustment_required(branch_id=5, delivery_order_id=22, item_id=9, folio="DEL-22")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT sucursal_id, severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert int(row["sucursal_id"]) == 5
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "adjustment_required:22:9"
    assert row["titulo"] == "Ajuste pendiente de autorización"


def test_adjustment_accepted_notification_uses_success_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_adjustment_accepted(branch_id=6, delivery_order_id=40, item_id=5, folio="DEL-40")
    ok2 = svc.notify_adjustment_accepted(branch_id=6, delivery_order_id=40, item_id=5, folio="DEL-40")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "success"
    assert row["dedupe_key"] == "adjustment_accepted:40:5"
    assert row["titulo"] == "Cliente aceptó ajuste"


def test_adjustment_rejected_notification_uses_warning_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_adjustment_rejected(branch_id=6, delivery_order_id=40, item_id=5, folio="DEL-40")
    ok2 = svc.notify_adjustment_rejected(branch_id=6, delivery_order_id=40, item_id=5, folio="DEL-40")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "adjustment_rejected:40:5"
    assert row["titulo"] == "Cliente rechazó ajuste"


def test_advance_paid_notification_uses_success_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_advance_paid(branch_id=7, sale_id=91, folio="VTA-91", amount=150.0)
    ok2 = svc.notify_advance_paid(branch_id=7, sale_id=91, folio="VTA-91", amount=150.0)

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo, cuerpo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "success"
    assert row["dedupe_key"] == "advance_paid:91"
    assert row["titulo"] == "Anticipo pagado"
    assert "$150.00" in row["cuerpo"]


def test_order_ready_counter_and_delivery_notifications_use_expected_dedupe_keys():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    assert svc.notify_order_ready_counter(branch_id=8, sale_id=301, folio="VTA-301") is True
    assert svc.notify_order_ready_counter(branch_id=8, sale_id=301, folio="VTA-301") is False
    assert svc.notify_order_ready_delivery(branch_id=8, sale_id=302, folio="VTA-302") is True
    assert svc.notify_order_ready_delivery(branch_id=8, sale_id=302, folio="VTA-302") is False

    rows = db.execute("SELECT dedupe_key, titulo FROM notification_inbox ORDER BY id").fetchall()
    assert rows[0]["dedupe_key"] == "ready_counter:301"
    assert rows[0]["titulo"] == "Pedido listo para mostrador"
    assert rows[1]["dedupe_key"] == "ready_delivery:302"
    assert rows[1]["titulo"] == "Pedido listo para reparto"


def test_scheduled_order_due_soon_notification_uses_warning_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_scheduled_order_due_soon(branch_id=9, sale_id=501, folio="VTA-501", scheduled_at="2026-06-30 08:00:00")
    ok2 = svc.notify_scheduled_order_due_soon(branch_id=9, sale_id=501, folio="VTA-501", scheduled_at="2026-06-30 08:00:00")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "scheduled_due_soon:501"
    assert row["titulo"] == "Pedido programado próximo"


def test_quote_created_notification_uses_info_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_quote_created(branch_id=10, quote_id=700, folio="COT-700", total=420.0)
    ok2 = svc.notify_quote_created(branch_id=10, quote_id=700, folio="COT-700", total=420.0)

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo, cuerpo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "info"
    assert row["dedupe_key"] == "quote_created:700"
    assert row["titulo"] == "Nueva cotización WhatsApp"
    assert "COT-700" in row["cuerpo"]


def test_order_delayed_notification_uses_warning_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_order_delayed(branch_id=11, sale_id=801, folio="VTA-801", reason="Tráfico")
    ok2 = svc.notify_order_delayed(branch_id=11, sale_id=801, folio="VTA-801", reason="Tráfico")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo, cuerpo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "order_delayed:801"
    assert row["titulo"] == "Pedido retrasado"
    assert "Tráfico" in row["cuerpo"]


def test_order_cancelled_by_customer_notification_uses_critical_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_order_cancelled_by_customer(branch_id=12, sale_id=901, folio="VTA-901")
    ok2 = svc.notify_order_cancelled_by_customer(branch_id=12, sale_id=901, folio="VTA-901")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "critical"
    assert row["dedupe_key"] == "order_cancelled_customer:901"
    assert row["titulo"] == "Pedido cancelado por cliente"


def test_quote_rejected_notification_uses_warning_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_quote_rejected(branch_id=13, quote_id=990, folio="COT-990")
    ok2 = svc.notify_quote_rejected(branch_id=13, quote_id=990, folio="COT-990")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "quote_rejected:990"
    assert row["titulo"] == "Cotización rechazada"


def test_order_in_route_notification_uses_info_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_order_in_route(branch_id=14, sale_id=1001, folio="VTA-1001")
    ok2 = svc.notify_order_in_route(branch_id=14, sale_id=1001, folio="VTA-1001")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "info"
    assert row["dedupe_key"] == "order_in_route:1001"
    assert row["titulo"] == "Pedido en reparto"


def test_order_delivered_notification_uses_success_and_dedupe_key():
    db = _db()
    snd = DummySound()
    svc = DesktopNotificationService(db, sound_service=snd)

    ok1 = svc.notify_order_delivered(branch_id=15, sale_id=1111, folio="VTA-1111")
    ok2 = svc.notify_order_delivered(branch_id=15, sale_id=1111, folio="VTA-1111")

    assert ok1 is True
    assert ok2 is False
    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox LIMIT 1").fetchone()
    assert row["severity"] == "success"
    assert row["dedupe_key"] == "order_delivered:1111"
    assert row["titulo"] == "Pedido entregado"
