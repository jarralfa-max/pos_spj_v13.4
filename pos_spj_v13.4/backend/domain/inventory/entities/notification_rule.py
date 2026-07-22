"""NotificationRule — routes an inventory alert event to a recipient (§55).

A rule says: when ``event_name`` fires within ``scope`` at or above
``min_severity``, notify ``recipient`` over ``channel`` — with an optional
throttle window that suppresses repeats. Config value object; no money, no
Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.inventory.enums import (
    NotificationChannel,
    NotificationRecipientType,
    NotificationSeverity,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class NotificationRule:
    id: str
    event_name: str
    channel: NotificationChannel
    recipient_type: NotificationRecipientType
    recipient_ref: str
    scope_type: str = "GLOBAL"
    scope_id: str = ""
    min_severity: NotificationSeverity = NotificationSeverity.INFO
    throttle_seconds: int = 0
    active: bool = True
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, event_name: str, channel: NotificationChannel,
               recipient_type: NotificationRecipientType, recipient_ref: str,
               scope_type: str = "GLOBAL", scope_id: str = "",
               min_severity: NotificationSeverity = NotificationSeverity.INFO,
               throttle_seconds: int = 0, active: bool = True) -> "NotificationRule":
        if not event_name:
            raise InventoryDomainError("La regla de notificación requiere evento")
        if not recipient_ref:
            raise InventoryDomainError("La regla de notificación requiere destinatario")
        if throttle_seconds < 0:
            raise InventoryDomainError("El throttle no puede ser negativo")
        return cls(id=new_uuid(), event_name=event_name, channel=channel,
                   recipient_type=recipient_type, recipient_ref=recipient_ref,
                   scope_type=scope_type, scope_id=scope_id, min_severity=min_severity,
                   throttle_seconds=throttle_seconds, active=active)
