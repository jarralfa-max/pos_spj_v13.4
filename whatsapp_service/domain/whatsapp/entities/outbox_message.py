# domain/whatsapp/entities/outbox_message.py — WA-17 (§21-22 del prompt maestro)
"""
OutboxMessage — respalda `whatsapp_outbox` (WA-3, migración 243). Cierra
el hallazgo original de WA-0/WA-3: "el microservicio envía mensajes
síncronamente, sin outbox persistido" (real gap frente a "un solo
sender/un solo outbox" del prompt maestro).

`message_id`/`conversation_id`/`channel_number_id` son opcionales
(reflejan el esquema real, sin `NOT NULL`) — no se fuerza que cada envío
en cola tenga primero un `WhatsAppMessage` (WA-2) creado; eso sería una
segunda pieza de trabajo (el ciclo de vida completo mensaje saliente →
delivery) fuera del alcance concreto de esta fase, que es "colar y
despachar", no "modelar cada envío como una entidad de mensaje".

Backoff simple (no exponencial "real" con jitter — suficiente para un
solo proceso, mismo criterio pragmático que `InboxWorker`, WA-6):
`BACKOFF_SECONDS[attempts - 1]`, tope en el último valor.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_OUTBOX_STATUSES, OutboxMessageStatus
from domain.whatsapp.exceptions import WhatsAppDomainError

MAX_ATTEMPTS = 5
BACKOFF_SECONDS = (30, 120, 600, 1800, 3600)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OutboxMessageAlreadyFinalizedError(WhatsAppDomainError):
    """El mensaje ya está SENT/DEAD_LETTER — no se puede volver a
    resolver."""


def _backoff_seconds(attempts: int) -> int:
    index = min(max(attempts, 1), len(BACKOFF_SECONDS)) - 1
    return BACKOFF_SECONDS[index]


@dataclass
class OutboxMessage:
    id: str
    conversation_id: Optional[str]
    channel_number_id: Optional[str]
    destination_phone: str
    payload_json: str
    template_name: Optional[str]
    operation_id: Optional[str]
    message_id: Optional[str]
    status: OutboxMessageStatus
    attempts: int
    last_error: Optional[str]
    next_retry_at: Optional[datetime]
    created_at: datetime
    processed_at: Optional[datetime]

    @classmethod
    def _new(
        cls, *, destination_phone: str, payload: Dict[str, Any], template_name: Optional[str] = None,
        conversation_id: Optional[str] = None, channel_number_id: Optional[str] = None,
        operation_id: Optional[str] = None, message_id: Optional[str] = None,
    ) -> "OutboxMessage":
        if not destination_phone:
            raise ValueError("destination_phone es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            channel_number_id=channel_number_id,
            destination_phone=destination_phone,
            payload_json=json.dumps(payload, ensure_ascii=False),
            template_name=template_name,
            operation_id=operation_id,
            message_id=message_id,
            status=OutboxMessageStatus.PENDING,
            attempts=0,
            last_error=None,
            next_retry_at=None,
            created_at=now,
            processed_at=None,
        )

    @classmethod
    def enqueue_text(
        cls, *, destination_phone: str, body: str, conversation_id: Optional[str] = None,
        channel_number_id: Optional[str] = None, operation_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> "OutboxMessage":
        if not body.strip():
            raise ValueError("body es obligatorio")
        return cls._new(
            destination_phone=destination_phone, payload={"kind": "text", "body": body},
            conversation_id=conversation_id, channel_number_id=channel_number_id,
            operation_id=operation_id, message_id=message_id,
        )

    @classmethod
    def enqueue_template(
        cls, *, destination_phone: str, template_name: str, language: str = "es_MX",
        parameters: Optional[Dict[str, Any]] = None, conversation_id: Optional[str] = None,
        channel_number_id: Optional[str] = None, operation_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> "OutboxMessage":
        if not template_name:
            raise ValueError("template_name es obligatorio")
        return cls._new(
            destination_phone=destination_phone,
            payload={
                "kind": "template", "template_name": template_name, "language": language,
                "parameters": parameters or {},
            },
            template_name=template_name, conversation_id=conversation_id,
            channel_number_id=channel_number_id, operation_id=operation_id, message_id=message_id,
        )

    @property
    def payload(self) -> Dict[str, Any]:
        return json.loads(self.payload_json)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_OUTBOX_STATUSES

    def _assert_not_terminal(self) -> None:
        if self.is_terminal():
            raise OutboxMessageAlreadyFinalizedError(f"OutboxMessage {self.id} ya está {self.status.value}")

    def is_due(self, *, now: Optional[datetime] = None) -> bool:
        if self.status != OutboxMessageStatus.PENDING:
            return False
        if self.next_retry_at is None:
            return True
        reference = now or _utcnow()
        next_retry = self.next_retry_at
        if next_retry.tzinfo is None:
            next_retry = next_retry.replace(tzinfo=timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return reference >= next_retry

    def claim(self) -> None:
        self._assert_not_terminal()
        self.attempts += 1

    def mark_sent(self) -> None:
        self._assert_not_terminal()
        self.status = OutboxMessageStatus.SENT
        self.processed_at = _utcnow()
        self.next_retry_at = None

    def mark_failed(self, error: str) -> None:
        self._assert_not_terminal()
        self.last_error = error
        if self.attempts >= MAX_ATTEMPTS:
            self.status = OutboxMessageStatus.DEAD_LETTER
            self.processed_at = _utcnow()
            self.next_retry_at = None
        else:
            self.status = OutboxMessageStatus.PENDING
            self.next_retry_at = _utcnow() + timedelta(seconds=_backoff_seconds(self.attempts))
