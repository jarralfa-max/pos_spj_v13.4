"""Base types for the notification system."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class NotificationPayload:
    """Carrier for a single notification.

    channel hints which channel(s) should handle it ("sound", "toast",
    "whatsapp", "desktop", "all").  DeliveryNotificationService uses this
    to route to the correct handler(s).
    """
    event_type: str                  # e.g. "delivery_new", "delivery_delivered"
    title: str
    body: str
    channel: str = "all"             # "all" | "sound" | "toast" | "whatsapp" | "desktop"
    order_id: Optional[int] = None
    cliente_tel: Optional[str] = None
    folio: Optional[str] = None
    priority: str = "normal"         # "low" | "normal" | "high" | "urgent"
    sucursal_id: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


class NotificationChannel(ABC):
    """Single-responsibility notification channel.

    Implementations must be fault-tolerant: never raise from send().
    """

    @abstractmethod
    def send(self, payload: NotificationPayload) -> bool:
        """Deliver notification. Returns True on success, False on failure."""

    def is_available(self) -> bool:
        """Return False if the channel cannot deliver (missing dependency etc)."""
        return True
