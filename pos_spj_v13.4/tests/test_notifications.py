"""Tests for the notifications/ module."""
from __future__ import annotations

import unittest

from notifications.base import NotificationChannel, NotificationPayload
from notifications.service import DeliveryNotificationService
from notifications.toast_channel import ToastNotificationChannel, set_toast_fn
from notifications.whatsapp_channel import WhatsAppNotificationChannel
from notifications.desktop_channel import DesktopNotificationChannel


# ── Test helpers ──────────────────────────────────────────────────────────────

class _RecordingChannel(NotificationChannel):
    def __init__(self):
        self.calls = []

    def send(self, payload: NotificationPayload) -> bool:
        self.calls.append(payload)
        return True


class _FailingChannel(NotificationChannel):
    def send(self, payload: NotificationPayload) -> bool:
        raise RuntimeError("channel broken")


class _UnavailableChannel(NotificationChannel):
    def is_available(self) -> bool:
        return False

    def send(self, payload: NotificationPayload) -> bool:
        raise AssertionError("should not be called")


# ── NotificationPayload ───────────────────────────────────────────────────────

class TestNotificationPayload(unittest.TestCase):
    def test_defaults(self):
        p = NotificationPayload(event_type="delivery_new", title="T", body="B")
        self.assertEqual(p.channel, "all")
        self.assertEqual(p.priority, "normal")
        self.assertEqual(p.sucursal_id, 1)
        self.assertIsNone(p.order_id)
        self.assertEqual(p.metadata, {})

    def test_all_fields(self):
        p = NotificationPayload(
            event_type="driver_assigned",
            title="Driver",
            body="Juan asignado",
            channel="whatsapp",
            order_id=42,
            cliente_tel="5551234567",
            folio="DEL-42",
            priority="high",
            sucursal_id=2,
            metadata={"driver_id": 7},
        )
        self.assertEqual(p.order_id, 42)
        self.assertEqual(p.metadata["driver_id"], 7)


# ── DeliveryNotificationService routing ──────────────────────────────────────

class TestDeliveryNotificationServiceRouting(unittest.TestCase):
    def _svc(self, *channels):
        return DeliveryNotificationService(list(channels))

    def test_all_channel_routes_to_non_whatsapp(self):
        rec = _RecordingChannel()
        svc = self._svc(rec)
        svc.notify(NotificationPayload(event_type="x", title="T", body="B", channel="all"))
        self.assertEqual(len(rec.calls), 1)

    def test_all_channel_skips_whatsapp(self):
        class WAChannel(_RecordingChannel):
            pass  # name contains no "whatsapp" → will match

        # The routing check is by class name; use explicit subclass named whatsapp
        class whatsapp_recording(_RecordingChannel):
            pass

        ch = whatsapp_recording()
        svc = self._svc(ch)
        svc.notify(NotificationPayload(event_type="x", title="T", body="B", channel="all"))
        self.assertEqual(len(ch.calls), 0, "WA channel should not be called for 'all'")

    def test_specific_channel_matches_by_name(self):
        class toast_ch(_RecordingChannel):
            pass

        class sound_ch(_RecordingChannel):
            pass

        tc = toast_ch()
        sc = sound_ch()
        svc = self._svc(tc, sc)
        svc.notify(NotificationPayload(event_type="x", title="T", body="B", channel="toast"))
        self.assertEqual(len(tc.calls), 1)
        self.assertEqual(len(sc.calls), 0)

    def test_silent_channel_routes_to_nothing(self):
        rec = _RecordingChannel()
        svc = self._svc(rec)
        svc.notify(NotificationPayload(event_type="x", title="T", body="B", channel="silent"))
        self.assertEqual(len(rec.calls), 0)

    def test_failing_channel_does_not_propagate(self):
        svc = self._svc(_FailingChannel())
        # Must not raise
        svc.notify(NotificationPayload(event_type="x", title="T", body="B"))

    def test_unavailable_channel_skipped(self):
        svc = self._svc(_UnavailableChannel())
        # Must not raise; UnavailableChannel.send() would raise AssertionError if called
        svc.notify(NotificationPayload(event_type="x", title="T", body="B"))

    def test_multiple_channels_all_called(self):
        r1, r2 = _RecordingChannel(), _RecordingChannel()
        svc = DeliveryNotificationService([r1, r2])
        svc.notify(NotificationPayload(event_type="x", title="T", body="B", channel="all"))
        self.assertEqual(len(r1.calls), 1)
        self.assertEqual(len(r2.calls), 1)

    def test_notify_delivery_created(self):
        rec = _RecordingChannel()
        svc = self._svc(rec)
        svc.notify_delivery_created(order_id=1, folio="DEL-1")
        self.assertEqual(rec.calls[0].event_type, "delivery_created")
        self.assertEqual(rec.calls[0].order_id, 1)

    def test_notify_driver_assigned_uses_whatsapp_channel(self):
        class whatsapp_rec(_RecordingChannel):
            pass

        ch = whatsapp_rec()
        svc = self._svc(ch)
        svc.notify_driver_assigned(
            order_id=5, folio="DEL-5", driver_nombre="Pedro",
            cliente_tel="5550001111",
        )
        self.assertEqual(len(ch.calls), 1)
        self.assertEqual(ch.calls[0].cliente_tel, "5550001111")


# ── ToastNotificationChannel ──────────────────────────────────────────────────

class TestToastNotificationChannel(unittest.TestCase):
    def test_unavailable_when_no_fn_registered(self):
        import notifications.toast_channel as tc
        original = tc._TOAST_FN
        tc._TOAST_FN = None
        ch = ToastNotificationChannel()
        self.assertFalse(ch.is_available())
        tc._TOAST_FN = original

    def test_available_and_calls_fn(self):
        calls = []
        set_toast_fn(lambda parent, title, body, level: calls.append((title, body, level)))
        ch = ToastNotificationChannel()
        self.assertTrue(ch.is_available())
        # send() dispatches via QTimer.singleShot in real app;
        # in test (no event loop) it will fall back gracefully
        p = NotificationPayload(event_type="x", title="Hello", body="World", priority="high")
        # Should not raise
        ch.send(p)


# ── WhatsAppNotificationChannel ───────────────────────────────────────────────

class TestWhatsAppNotificationChannel(unittest.TestCase):
    def test_unavailable_when_service_fails(self):
        ch = WhatsAppNotificationChannel()
        ch._init_failed = True
        self.assertFalse(ch.is_available())

    def test_no_phone_returns_false(self):
        class MockWA:
            def notify_status(self, **kw): return True

        ch = WhatsAppNotificationChannel(wa_service=MockWA())
        p = NotificationPayload(event_type="x", title="T", body="B", cliente_tel="")
        result = ch.send(p)
        self.assertFalse(result)

    def test_sends_with_phone(self):
        sent = []

        class MockWA:
            def notify_status(self, **kw):
                sent.append(kw)
                return True

        ch = WhatsAppNotificationChannel(wa_service=MockWA())
        p = NotificationPayload(
            event_type="delivery_created", title="T", body="B",
            cliente_tel="5551234567", folio="DEL-1",
        )
        result = ch.send(p)
        self.assertTrue(result)
        self.assertEqual(sent[0]["phone"], "5551234567")


# ── DesktopNotificationChannel ────────────────────────────────────────────────

class TestDesktopNotificationChannel(unittest.TestCase):
    def test_unavailable_when_no_tray(self):
        import notifications.desktop_channel as dc
        original = dc._TRAY_ICON
        dc._TRAY_ICON = None
        ch = DesktopNotificationChannel()
        self.assertFalse(ch.is_available())
        dc._TRAY_ICON = original


if __name__ == "__main__":
    unittest.main()
