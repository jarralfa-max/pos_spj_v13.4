"""NotificationAccount — SET-20 "Accounts": the sender identity for one
notification channel (e.g. our WhatsApp Business number, our SMTP
account). `credential_reference` is a `SecretStoreGateway` secret name —
never a raw secret, same discipline
`backend.domain.integrations.entities.integration_instance.
IntegrationInstance.credential_references` already established (SET-19).

`integration_instance_id` is an optional, opaque link back into SET-19's
`IntegrationInstance` catalog (e.g. this account's underlying WhatsApp
`IntegrationInstance`) — never resolved or validated here, the same
"opaque reference, not a real dependency" discipline
`PrintJob.source_document_id` already established (Document Output,
SET-11). Notifications never imports the Integrations bounded context.
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
class NotificationAccount:
    id: str
    channel: NotificationChannel
    name: str
    credential_reference: str | None = None
    integration_instance_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, channel: NotificationChannel, name: str, credential_reference: str | None = None,
        integration_instance_id: str | None = None,
    ) -> "NotificationAccount":
        if not name.strip():
            raise NotificationsInvalidValueError("name es obligatorio")
        return cls(
            id=new_uuid(), channel=channel, name=name.strip(), credential_reference=credential_reference,
            integration_instance_id=(
                validate_uuidv7(integration_instance_id) if integration_instance_id else None
            ),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, name: str, credential_reference: str | None = None) -> None:
        if not name.strip():
            raise NotificationsInvalidValueError("name es obligatorio")
        self.name = name.strip()
        self.credential_reference = credential_reference
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
