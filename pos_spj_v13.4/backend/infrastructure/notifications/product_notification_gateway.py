"""ProductNotificationGateway (PROD-16, §36) — real fan-out to in-app + WhatsApp.

The module's own docstring (`backend/application/products/notifications/
gateway.py`) always described production as "a fan-out to in-app + WhatsApp"
— this is that fan-out, finally built. Routes by `channel` to the matching
real notifier (`InAppProductNotifier`/`WhatsAppProductNotifier`); an unknown
channel is a no-op (never raises — a delivery failure must never break the
caller, same discipline `ProductNotificationService.notify()` already applies
one level up).
"""

from __future__ import annotations

from backend.domain.products.notification_enums import NotificationChannel
from backend.infrastructure.notifications.in_app_product_notifier import (
    InAppProductNotifier,
)
from backend.infrastructure.notifications.whatsapp_product_notifier import (
    WhatsAppProductNotifier,
)


class FanOutProductNotificationGateway:
    def __init__(self, connection) -> None:
        self._in_app = InAppProductNotifier(connection)
        self._whatsapp = WhatsAppProductNotifier(connection)

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        if channel == NotificationChannel.IN_APP.value:
            self._in_app.send(channel=channel, recipient_ref=recipient_ref,
                              message=message, context=context)
        elif channel == NotificationChannel.WHATSAPP.value:
            self._whatsapp.send(channel=channel, recipient_ref=recipient_ref,
                                message=message, context=context)
