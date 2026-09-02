"""NotificationTemplate — SET-20 "Templates": generalizes the real,
hardcoded `TEMPLATES` catalog in `whatsapp_service/messaging/templates.py`
(9 Meta-approved WhatsApp templates — `pedido_confirmado`, `pedido_listo`,
`anticipo_requerido`, ...) into persisted, admin-manageable data. Same
`code`/`language`/`parameter_names` shape as that dict — not invented.

WhatsApp only allows pre-approved template messages outside the 24h
customer-service window (the comment at the top of that module says so
directly) — Meta's approval itself happens outside this system, on
Meta's own dashboard; `active` here means "an admin confirmed Meta
approved it and it's safe to send", not that this bounded context
performs the approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import NotificationsInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class NotificationTemplate:
    id: str
    code: str
    channel: NotificationChannel
    language: str
    parameter_names: tuple[str, ...] = ()
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, channel: NotificationChannel, language: str,
        parameter_names: tuple[str, ...] | list[str] = (),
    ) -> "NotificationTemplate":
        if not code.strip():
            raise NotificationsInvalidValueError("code es obligatorio")
        if not language.strip():
            raise NotificationsInvalidValueError("language es obligatorio")
        names = tuple(parameter_names)
        if len(names) != len(set(names)):
            raise NotificationsInvalidValueError(f"parameter_names no puede tener duplicados: {names}")
        return cls(
            id=new_uuid(), code=code.strip(), channel=channel, language=language.strip(),
            parameter_names=names,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_parameter_names(self, parameter_names: tuple[str, ...] | list[str] = ()) -> None:
        names = tuple(parameter_names)
        if len(names) != len(set(names)):
            raise NotificationsInvalidValueError(f"parameter_names no puede tener duplicados: {names}")
        self.parameter_names = names
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
