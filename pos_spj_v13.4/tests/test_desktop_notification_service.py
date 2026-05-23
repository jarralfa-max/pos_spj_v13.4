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
