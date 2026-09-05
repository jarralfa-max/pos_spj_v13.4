# domain/whatsapp/entities/inbox_job.py — WA-6 (prompt maestro §20-21)
"""InboundMessageJob — un job de procesamiento asíncrono para un mensaje
entrante ya persistido (`WhatsAppMessage`, WA-2). El webhook (WA-6) solo
valida + persiste + crea este job + responde 200 — procesar la intención
real es trabajo de un worker separado, no del handler HTTP."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.whatsapp._ids import new_id
from domain.whatsapp.enums import TERMINAL_INBOX_STATUSES, InboxStatus
from domain.whatsapp.exceptions import InvalidInboxJobTransitionError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_VALID_TRANSITIONS = {
    InboxStatus.PENDING: {InboxStatus.PROCESSING},
    InboxStatus.PROCESSING: {InboxStatus.COMPLETED, InboxStatus.FAILED},
    InboxStatus.FAILED: {InboxStatus.RETRY, InboxStatus.DEAD_LETTER},
    InboxStatus.RETRY: {InboxStatus.PROCESSING, InboxStatus.DEAD_LETTER},
    InboxStatus.COMPLETED: set(),
    InboxStatus.DEAD_LETTER: set(),
}


@dataclass
class InboundMessageJob:
    id: str
    message_id: str
    status: InboxStatus
    attempts: int
    last_error: Optional[str]
    locked_at: Optional[datetime]
    created_at: datetime
    processed_at: Optional[datetime]

    @classmethod
    def create(cls, *, message_id: str) -> "InboundMessageJob":
        if not message_id:
            raise ValueError("message_id es obligatorio")
        return cls(
            id=new_id(),
            message_id=message_id,
            status=InboxStatus.PENDING,
            attempts=0,
            last_error=None,
            locked_at=None,
            created_at=_utcnow(),
            processed_at=None,
        )

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_INBOX_STATUSES

    def _transition(self, new_status: InboxStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InvalidInboxJobTransitionError(
                f"InboundMessageJob {self.id} no puede pasar de {self.status.value} a "
                f"{new_status.value} (permitidos: {sorted(s.value for s in allowed)})"
            )
        self.status = new_status

    def claim(self) -> None:
        """Un worker reclama el job (PENDING/RETRY -> PROCESSING)."""
        self._transition(InboxStatus.PROCESSING)
        self.attempts += 1
        self.locked_at = _utcnow()

    def complete(self) -> None:
        self._transition(InboxStatus.COMPLETED)
        self.processed_at = _utcnow()
        self.locked_at = None

    def fail(self, error: str) -> None:
        self._transition(InboxStatus.FAILED)
        self.last_error = error
        self.locked_at = None

    def schedule_retry(self) -> None:
        self._transition(InboxStatus.RETRY)

    def move_to_dead_letter(self, error: Optional[str] = None) -> None:
        self._transition(InboxStatus.DEAD_LETTER)
        if error:
            self.last_error = error
        self.processed_at = _utcnow()
        self.locked_at = None
