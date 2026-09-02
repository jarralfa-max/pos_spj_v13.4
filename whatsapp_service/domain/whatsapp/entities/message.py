# domain/whatsapp/entities/message.py — WA-2 (prompt maestro §15)
"""WhatsAppMessage y WhatsAppMessageDelivery."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import (
    TERMINAL_DELIVERY_STATUSES,
    MessageDeliveryStatus,
    MessageDirection,
    MessageType,
)
from domain.whatsapp.exceptions import InvalidMessageDeliveryTransitionError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WhatsAppMessage:
    id: str
    conversation_id: str
    direction: MessageDirection
    message_type: MessageType
    provider_message_id: Optional[str]
    payload_reference: Optional[str]
    correlation_id: Optional[str]
    operation_id: Optional[str]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        conversation_id: str,
        direction: MessageDirection,
        message_type: MessageType,
        provider_message_id: Optional[str] = None,
        payload_reference: Optional[str] = None,
        correlation_id: Optional[str] = None,
        operation_id: Optional[str] = None,
    ) -> "WhatsAppMessage":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            direction=direction,
            message_type=message_type,
            provider_message_id=provider_message_id,
            payload_reference=payload_reference,
            correlation_id=correlation_id,
            operation_id=operation_id,
            created_at=_utcnow(),
        )


# Transiciones válidas de estado de entrega (§15 — no toda transición es
# posible: un mensaje FAILED puede reintentarse (RETRYING) pero uno
# CANCELLED o DEAD_LETTER no vuelve a moverse).
_VALID_DELIVERY_TRANSITIONS = {
    MessageDeliveryStatus.QUEUED: {
        MessageDeliveryStatus.VALIDATING,
        MessageDeliveryStatus.SENT,
        MessageDeliveryStatus.FAILED,
        MessageDeliveryStatus.CANCELLED,
    },
    MessageDeliveryStatus.VALIDATING: {
        MessageDeliveryStatus.SENT,
        MessageDeliveryStatus.FAILED,
        MessageDeliveryStatus.CANCELLED,
    },
    MessageDeliveryStatus.SENT: {
        MessageDeliveryStatus.DELIVERED,
        MessageDeliveryStatus.FAILED,
    },
    MessageDeliveryStatus.DELIVERED: {MessageDeliveryStatus.READ},
    MessageDeliveryStatus.FAILED: {
        MessageDeliveryStatus.RETRYING,
        MessageDeliveryStatus.DEAD_LETTER,
    },
    MessageDeliveryStatus.RETRYING: {
        MessageDeliveryStatus.SENT,
        MessageDeliveryStatus.FAILED,
        MessageDeliveryStatus.DEAD_LETTER,
    },
    MessageDeliveryStatus.READ: set(),
    MessageDeliveryStatus.DEAD_LETTER: set(),
    MessageDeliveryStatus.CANCELLED: set(),
}


@dataclass
class WhatsAppMessageDelivery:
    id: str
    message_id: str
    status: MessageDeliveryStatus
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    failed_at: Optional[datetime]
    error_code: Optional[str]
    attempt_count: int
    updated_at: datetime

    @classmethod
    def create(cls, *, message_id: str) -> "WhatsAppMessageDelivery":
        if not message_id:
            raise ValueError("message_id es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            message_id=message_id,
            status=MessageDeliveryStatus.QUEUED,
            sent_at=None,
            delivered_at=None,
            read_at=None,
            failed_at=None,
            error_code=None,
            attempt_count=0,
            updated_at=now,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_DELIVERY_STATUSES

    def transition_to(
        self, new_status: MessageDeliveryStatus, *, error_code: Optional[str] = None
    ) -> None:
        allowed = _VALID_DELIVERY_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidMessageDeliveryTransitionError(
                f"Delivery {self.id} no puede pasar de {self.status.value} a "
                f"{new_status.value} (permitidos: {sorted(s.value for s in allowed)})"
            )
        now = _utcnow()
        self.status = new_status
        self.updated_at = now
        if new_status in (MessageDeliveryStatus.SENT, MessageDeliveryStatus.RETRYING):
            self.attempt_count += 1
            if new_status == MessageDeliveryStatus.SENT:
                self.sent_at = now
        elif new_status == MessageDeliveryStatus.DELIVERED:
            self.delivered_at = now
        elif new_status == MessageDeliveryStatus.READ:
            self.read_at = now
        elif new_status == MessageDeliveryStatus.FAILED:
            self.failed_at = now
            self.error_code = error_code
