# domain/whatsapp/entities/conversation.py — WA-2 (prompt maestro §14)
"""WhatsAppConversation y ConversationSession."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.entities.conversation_context import ConversationContext
from domain.whatsapp.enums import TERMINAL_CONVERSATION_STATES, ConversationState
from domain.whatsapp.exceptions import InvalidConversationStateTransitionError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConversationSession:
    """Una sesión dentro de una conversación (§14) — permite reabrir el hilo
    (nueva sesión) sin perder el historial de la conversación misma."""

    id: str
    conversation_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    @classmethod
    def start(cls, *, conversation_id: str) -> "ConversationSession":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        return cls(id=new_id(), conversation_id=conversation_id, started_at=_utcnow())

    def end(self) -> None:
        if self.ended_at is None:
            self.ended_at = _utcnow()

    def is_active(self) -> bool:
        return self.ended_at is None


@dataclass
class WhatsAppConversation:
    id: str
    identity_id: str
    channel_number_id: str
    branch_id: Optional[str]
    state: ConversationState
    context: ConversationContext
    current_session_id: Optional[str]
    opened_at: datetime
    closed_at: Optional[datetime]
    last_message_at: Optional[datetime]
    updated_at: datetime

    @classmethod
    def open(
        cls,
        *,
        identity_id: str,
        channel_number_id: str,
        branch_id: Optional[str] = None,
    ) -> "WhatsAppConversation":
        if not identity_id:
            raise ValueError("identity_id es obligatorio")
        if not channel_number_id:
            raise ValueError("channel_number_id es obligatorio")
        now = _utcnow()
        return cls(
            id=new_id(),
            identity_id=identity_id,
            channel_number_id=channel_number_id,
            branch_id=branch_id,
            state=ConversationState.OPEN,
            context=ConversationContext(customer_id=None, branch_id=branch_id),
            current_session_id=None,
            opened_at=now,
            closed_at=None,
            last_message_at=None,
            updated_at=now,
        )

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_CONVERSATION_STATES

    def transition_to(self, new_state: ConversationState) -> None:
        """Invariante mínimo de la entidad: un estado terminal no reabre.

        Decidir CUÁL es el siguiente estado correcto según intención/timeout
        es responsabilidad del motor conversacional (WA-7) — esta entidad
        solo protege que nadie reabra una conversación ya cerrada.
        """
        if self.is_terminal() and new_state not in TERMINAL_CONVERSATION_STATES:
            raise InvalidConversationStateTransitionError(
                f"Conversación {self.id} está en estado terminal {self.state.value}; "
                f"no puede transicionar a {new_state.value}"
            )
        self.state = new_state
        self.updated_at = _utcnow()
        if new_state == ConversationState.CLOSED and self.closed_at is None:
            self.closed_at = self.updated_at

    def record_inbound_message(self) -> None:
        self.last_message_at = _utcnow()
        self.updated_at = self.last_message_at

    def update_context(self, **changes) -> None:
        self.context = self.context.with_update(**changes)
        self.updated_at = _utcnow()

    def attach_session(self, session: ConversationSession) -> None:
        if session.conversation_id != self.id:
            raise ValueError("La sesión no pertenece a esta conversación")
        self.current_session_id = session.id
        self.updated_at = _utcnow()
