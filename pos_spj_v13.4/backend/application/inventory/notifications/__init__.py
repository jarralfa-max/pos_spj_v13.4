"""Inventory notifications / WhatsApp alerts (§55, INV-23)."""

from backend.application.inventory.notifications.gateway import (
    InMemoryNotificationGateway,
    InventoryNotificationGateway,
    NotificationDeliveryError,
)
from backend.application.inventory.notifications.notification_service import (
    InventoryNotificationService,
    SetNotificationRuleUseCase,
)

__all__ = [
    "InMemoryNotificationGateway",
    "InventoryNotificationGateway",
    "InventoryNotificationService",
    "NotificationDeliveryError",
    "SetNotificationRuleUseCase",
]
