"""NotificationRoute — SET-20 "Routing": which `NotificationTemplate` and
`NotificationAccount` handle a given ERP event code. Generalizes the
implicit routing `whatsapp_service/messaging/templates.py::
send_event_template(to, event_name, params)` already performs (event
name → template lookup) into explicit, admin-manageable data — and adds
the account selection that function never had to make (it always used
the one configured WhatsApp sender).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import NotificationsInvalidValueError
from backend.shared.ids import new_uuid, validate_uuidv7


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class NotificationRoute:
    id: str
    event_code: str
    channel: NotificationChannel
    template_id: str
    account_id: str
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, event_code: str, channel: NotificationChannel, template_id: str, account_id: str,
    ) -> "NotificationRoute":
        if not event_code.strip():
            raise NotificationsInvalidValueError("event_code es obligatorio")
        return cls(
            id=new_uuid(), event_code=event_code.strip(), channel=channel,
            template_id=validate_uuidv7(template_id), account_id=validate_uuidv7(account_id),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
