# domain/whatsapp/entities/handoff_request.py — WA-16 (§32 del prompt maestro)
"""
HandoffRequest — solicitud de traspaso a un agente humano. Distinto de
`ConversationState.HANDOFF_REQUESTED`/`HUMAN_ACTIVE` (WA-2/WA-7, el estado
de la conversación en sí): esta entidad es el registro propio de LA
SOLICITUD (motivo, a quién se asignó, cuándo se resolvió) — igual que
`OrderDraft` no es el pedido canónico, `HandoffRequest` no es el estado de
conversación, es su rastro operativo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_HANDOFF_STATUSES, HandoffStatus
from domain.whatsapp.exceptions import WhatsAppDomainError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HandoffRequestAlreadyFinalizedError(WhatsAppDomainError):
    """La solicitud ya está RESOLVED/CANCELLED — no se puede transicionar
    más."""


@dataclass
class HandoffRequest:
    id: str
    conversation_id: str
    branch_id: Optional[str]
    reason: str
    status: HandoffStatus
    assigned_to_phone: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    @classmethod
    def open(cls, *, conversation_id: str, reason: str, branch_id: Optional[str] = None) -> "HandoffRequest":
        if not conversation_id:
            raise ValueError("conversation_id es obligatorio")
        if not reason.strip():
            raise ValueError("reason es obligatorio — no se escala sin motivo")
        now = _utcnow()
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            branch_id=branch_id,
            reason=reason.strip(),
            status=HandoffStatus.OPEN,
            assigned_to_phone=None,
            created_at=now,
            updated_at=now,
            resolved_at=None,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_HANDOFF_STATUSES

    def _assert_not_terminal(self) -> None:
        if self.is_terminal():
            raise HandoffRequestAlreadyFinalizedError(
                f"HandoffRequest {self.id} ya está {self.status.value}"
            )

    def assign(self, staff_phone: str) -> None:
        self._assert_not_terminal()
        self.assigned_to_phone = staff_phone
        self.status = HandoffStatus.ASSIGNED
        self.updated_at = _utcnow()

    def resolve(self) -> None:
        self._assert_not_terminal()
        self.status = HandoffStatus.RESOLVED
        self.resolved_at = _utcnow()
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        self._assert_not_terminal()
        self.status = HandoffStatus.CANCELLED
        self.resolved_at = _utcnow()
        self.updated_at = _utcnow()
