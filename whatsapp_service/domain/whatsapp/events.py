# domain/whatsapp/events.py — WA-2 (prompt maestro §55)
"""
Eventos de dominio del canal WhatsApp — solo los que corresponden a las
entidades construidas en WA-2 (Conversation, Message, Identity). El resto
del catálogo canónico de §55 (`WHATSAPP_HANDOFF_*`, `WHATSAPP_OPT_OUT_*`,
`WHATSAPP_BUSINESS_OPERATION_*`) se agrega en las fases dueñas de esas
entidades (WA-16 Handoff, WA-14 Consentimiento, WA-9 Contratos ERP) — no se
inventan aquí por adelantado.

Estos son objetos de dominio puros (dataclasses), NO llamadas a
`core.events.event_bus` — esa integración de infraestructura es WA-4
(bootstrap) / WA-18 (notificaciones). Aquí solo se define QUÉ pasó.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp.enums import ConversationState, MessageDeliveryStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime


# ── Nombres canónicos (§55) cubiertos por WA-2 ──────────────────────────────
WHATSAPP_MESSAGE_RECEIVED = "WHATSAPP_MESSAGE_RECEIVED"
WHATSAPP_MESSAGE_DEDUPLICATED = "WHATSAPP_MESSAGE_DEDUPLICATED"
WHATSAPP_CONVERSATION_OPENED = "WHATSAPP_CONVERSATION_OPENED"
WHATSAPP_CONVERSATION_STATE_CHANGED = "WHATSAPP_CONVERSATION_STATE_CHANGED"
WHATSAPP_MESSAGE_QUEUED = "WHATSAPP_MESSAGE_QUEUED"
WHATSAPP_MESSAGE_SENT = "WHATSAPP_MESSAGE_SENT"
WHATSAPP_MESSAGE_DELIVERED = "WHATSAPP_MESSAGE_DELIVERED"
WHATSAPP_MESSAGE_READ = "WHATSAPP_MESSAGE_READ"
WHATSAPP_MESSAGE_FAILED = "WHATSAPP_MESSAGE_FAILED"
WHATSAPP_IDENTITY_RESOLVED = "WHATSAPP_IDENTITY_RESOLVED"
WHATSAPP_IDENTITY_BLOCKED = "WHATSAPP_IDENTITY_BLOCKED"


@dataclass(frozen=True)
class ConversationOpened(DomainEvent):
    conversation_id: str
    identity_id: str
    channel_number_id: str
    branch_id: Optional[str]

    @classmethod
    def of(cls, conversation) -> "ConversationOpened":
        return cls(
            occurred_at=_utcnow(),
            conversation_id=conversation.id,
            identity_id=conversation.identity_id,
            channel_number_id=conversation.channel_number_id,
            branch_id=conversation.branch_id,
        )


@dataclass(frozen=True)
class ConversationStateChanged(DomainEvent):
    conversation_id: str
    previous_state: ConversationState
    new_state: ConversationState


@dataclass(frozen=True)
class MessageReceived(DomainEvent):
    message_id: str
    conversation_id: str
    provider_message_id: Optional[str]

    @classmethod
    def of(cls, message) -> "MessageReceived":
        return cls(
            occurred_at=_utcnow(),
            message_id=message.id,
            conversation_id=message.conversation_id,
            provider_message_id=message.provider_message_id,
        )


@dataclass(frozen=True)
class MessageDeduplicated(DomainEvent):
    provider_message_id: str
    conversation_id: Optional[str]


@dataclass(frozen=True)
class MessageDeliveryStatusChanged(DomainEvent):
    delivery_id: str
    message_id: str
    previous_status: MessageDeliveryStatus
    new_status: MessageDeliveryStatus
    error_code: Optional[str] = None


@dataclass(frozen=True)
class IdentityResolved(DomainEvent):
    identity_id: str
    customer_id: str


@dataclass(frozen=True)
class IdentityBlocked(DomainEvent):
    identity_id: str
