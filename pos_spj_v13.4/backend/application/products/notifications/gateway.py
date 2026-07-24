"""ProductNotificationGateway — the outbound delivery port (§35, §36).

The notification service decides who/whether to notify, then hands the message to
a gateway to deliver. Production wires a fan-out to in-app + WhatsApp; the
in-memory one records deliveries for tests. A ``NotificationDeliveryError`` marks a
delivery as failed (logged, never crashes the caller).
"""

from __future__ import annotations

from typing import Protocol


class NotificationDeliveryError(Exception):
    """Raised by a gateway when a message could not be delivered."""


class ProductNotificationGateway(Protocol):
    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None: ...


class InMemoryProductNotifier:
    """Records delivered messages; used in tests and single-node setups."""

    def __init__(self) -> None:
        self.delivered: list[dict] = []

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        self.delivered.append({"channel": channel, "recipient_ref": recipient_ref,
                               "message": message, "context": context})
