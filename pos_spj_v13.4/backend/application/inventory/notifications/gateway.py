"""InventoryNotificationGateway — the outbound delivery port (§55).

The notification service is channel-agnostic: it decides *who* to notify and
*whether*, then hands a message to the gateway to actually deliver. Production
wires a gateway that fans out to WhatsApp / desktop / email; the in-memory one
records deliveries for tests and single-node setups. A ``NotificationDeliveryError``
marks a delivery as failed (logged FAILED, never crashes the caller).
"""

from __future__ import annotations

from typing import Protocol


class NotificationDeliveryError(Exception):
    """Raised by a gateway when a message could not be delivered."""


class InventoryNotificationGateway(Protocol):
    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None: ...


class InMemoryNotificationGateway:
    """Records delivered messages; used in tests and offline/single-node setups."""

    def __init__(self) -> None:
        self.delivered: list[dict] = []

    def send(self, *, channel: str, recipient_ref: str, message: str,
             context: dict) -> None:
        self.delivered.append({"channel": channel, "recipient_ref": recipient_ref,
                               "message": message, "context": context})
