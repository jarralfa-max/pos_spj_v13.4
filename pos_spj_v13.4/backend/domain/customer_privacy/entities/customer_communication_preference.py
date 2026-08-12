"""CustomerCommunicationPreference — one settings record per customer
(§44: "canal, horario, idioma, transaccional/operativo/marketing/
promociones/recordatorios; WhatsApp y Notification Management la
consumen"). A 1:1 record, not an append-only log — mirrors CRM-8's
CustomerCreditProfile.

``allow_transactional`` defaults ``True`` and is not meant to be turned off
by this entity alone — transactional messages (order confirmations,
receipts) are typically not opt-out-able by policy; the application layer
may still expose the flag for completeness, but nothing in this domain
enforces that constraint (out of scope: that is a Notification Management
policy decision, not this bounded context's).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_privacy.enums import PreferredChannel
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerCommunicationPreference:
    id: str
    customer_id: str
    preferred_channel: PreferredChannel = PreferredChannel.WHATSAPP
    preferred_language: str = "es"
    contact_hours_start: str | None = None
    contact_hours_end: str | None = None
    allow_transactional: bool = True
    allow_operational: bool = True
    allow_marketing: bool = False
    allow_promotions: bool = False
    allow_reminders: bool = True
    updated_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, customer_id: str, *, preferred_channel: PreferredChannel = PreferredChannel.WHATSAPP,
        preferred_language: str = "es", updated_by_user_id: str | None = None,
    ) -> "CustomerCommunicationPreference":
        if not customer_id:
            raise CustomerPrivacyDomainError("customer_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, preferred_channel=preferred_channel,
            preferred_language=preferred_language, updated_by_user_id=updated_by_user_id,
        )

    def update(
        self, *, updated_by_user_id: str, preferred_channel: PreferredChannel | None = None,
        preferred_language: str | None = None, contact_hours_start: str | None = None,
        contact_hours_end: str | None = None, allow_operational: bool | None = None,
        allow_marketing: bool | None = None, allow_promotions: bool | None = None,
        allow_reminders: bool | None = None,
    ) -> None:
        if not updated_by_user_id:
            raise CustomerPrivacyDomainError("update() requiere updated_by_user_id")
        if preferred_channel is not None:
            self.preferred_channel = preferred_channel
        if preferred_language is not None:
            self.preferred_language = preferred_language
        if contact_hours_start is not None:
            self.contact_hours_start = contact_hours_start
        if contact_hours_end is not None:
            self.contact_hours_end = contact_hours_end
        if allow_operational is not None:
            self.allow_operational = allow_operational
        if allow_marketing is not None:
            self.allow_marketing = allow_marketing
        if allow_promotions is not None:
            self.allow_promotions = allow_promotions
        if allow_reminders is not None:
            self.allow_reminders = allow_reminders
        self.updated_by_user_id = updated_by_user_id
        self.updated_at = _utcnow()
