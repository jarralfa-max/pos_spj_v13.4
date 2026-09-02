"""ORD-26 — DeliveryNotificationPolicy: which delivery events get a customer
WhatsApp message and/or an internal staff alert."""

from __future__ import annotations

from backend.domain.orders_delivery.events import DeliveryEvents
from backend.domain.orders_delivery.policies.notification_policy import DeliveryNotificationPolicy


class TestCustomerMessage:
    def test_dispatched_has_a_message(self):
        message = DeliveryNotificationPolicy.customer_message(
            DeliveryEvents.DISPATCHED, order_number="P-100")
        assert message is not None
        assert "P-100" in message

    def test_completed_has_a_message(self):
        message = DeliveryNotificationPolicy.customer_message(
            DeliveryEvents.COMPLETED, order_number="P-100")
        assert message is not None and "entregado" in message

    def test_failed_has_a_message(self):
        message = DeliveryNotificationPolicy.customer_message(
            DeliveryEvents.FAILED, order_number="P-100")
        assert message is not None and "No pudimos" in message

    def test_unrelated_event_has_no_message(self):
        assert DeliveryNotificationPolicy.customer_message(
            DeliveryEvents.DRIVER_ASSIGNED, order_number="P-100") is None


class TestInternalAlert:
    def test_failed_requires_internal_alert(self):
        assert DeliveryNotificationPolicy.requires_internal_alert(DeliveryEvents.FAILED) is True

    def test_settlement_difference_requires_internal_alert(self):
        assert DeliveryNotificationPolicy.requires_internal_alert(
            DeliveryEvents.DRIVER_SETTLEMENT_DIFFERENCE_DETECTED) is True

    def test_completed_does_not_require_internal_alert(self):
        assert DeliveryNotificationPolicy.requires_internal_alert(DeliveryEvents.COMPLETED) is False
