"""CRMActivity — a planned or logged interaction (§23-26): call, meeting,
visit, email, WhatsApp touch, follow-up, quote review, payment follow-up.

Status transitions:

    PLANNED ──start()──► IN_PROGRESS ──complete()──► COMPLETED (terminal)
       │                      │
       └──cancel(reason)──────┴──► CANCELLED (terminal)

    PLANNED/IN_PROGRESS ──reschedule(new_scheduled_at)──► (same status)

``effective_status()`` reports OVERDUE without ever persisting it — see
CRMWorkItemStatus's docstring for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType, CRMWorkItemStatus
from backend.domain.crm.exceptions import InvalidCRMActivityStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_STARTABLE = {CRMWorkItemStatus.PLANNED}
_COMPLETABLE = {CRMWorkItemStatus.PLANNED, CRMWorkItemStatus.IN_PROGRESS}
_CANCELLABLE = {CRMWorkItemStatus.PLANNED, CRMWorkItemStatus.IN_PROGRESS}
_RESCHEDULABLE = {CRMWorkItemStatus.PLANNED, CRMWorkItemStatus.IN_PROGRESS}
_OPEN_STATUSES = {CRMWorkItemStatus.PLANNED, CRMWorkItemStatus.IN_PROGRESS}


@dataclass(slots=True)
class CRMActivity:
    id: str
    activity_type: CRMActivityType
    related_entity_type: CRMRelatedEntityType
    related_entity_id: str
    subject: str
    status: CRMWorkItemStatus = CRMWorkItemStatus.PLANNED
    scheduled_at: str | None = None
    completed_at: str | None = None
    assigned_user_id: str | None = None
    description: str = ""
    created_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, activity_type: CRMActivityType, related_entity_type: CRMRelatedEntityType,
        related_entity_id: str, subject: str, *, scheduled_at: str | None = None,
        assigned_user_id: str | None = None, description: str = "",
        created_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CRMActivity":
        if not related_entity_id:
            raise InvalidCRMActivityStateError("related_entity_id es obligatorio")
        if not subject or not subject.strip():
            raise InvalidCRMActivityStateError("subject es obligatorio")
        return cls(
            id=new_uuid(), activity_type=activity_type, related_entity_type=related_entity_type,
            related_entity_id=related_entity_id, subject=subject.strip(),
            scheduled_at=scheduled_at, assigned_user_id=assigned_user_id,
            description=description, created_by_user_id=created_by_user_id,
            operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def start(self) -> None:
        if self.status not in _STARTABLE:
            raise InvalidCRMActivityStateError(f"No se puede iniciar desde {self.status.value}")
        self.status = CRMWorkItemStatus.IN_PROGRESS
        self._touch()

    def complete(self) -> None:
        if self.status not in _COMPLETABLE:
            raise InvalidCRMActivityStateError(f"No se puede completar desde {self.status.value}")
        self.status = CRMWorkItemStatus.COMPLETED
        self.completed_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in _CANCELLABLE:
            raise InvalidCRMActivityStateError(f"No se puede cancelar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCRMActivityStateError("Cancelar requiere un motivo")
        self.status = CRMWorkItemStatus.CANCELLED
        self._touch()

    def reschedule(self, new_scheduled_at: str) -> None:
        if self.status not in _RESCHEDULABLE:
            raise InvalidCRMActivityStateError(
                f"No se puede reprogramar desde {self.status.value}")
        if not new_scheduled_at:
            raise InvalidCRMActivityStateError("reschedule() requiere una nueva fecha")
        self.scheduled_at = new_scheduled_at
        self._touch()

    def reassign(self, user_id: str) -> None:
        if self.status not in _OPEN_STATUSES:
            raise InvalidCRMActivityStateError(
                f"No se puede reasignar desde {self.status.value}")
        if not user_id:
            raise InvalidCRMActivityStateError("reassign() requiere un usuario")
        self.assigned_user_id = user_id
        self._touch()

    def effective_status(self, *, as_of: str | None = None) -> CRMWorkItemStatus:
        if self.status not in _OPEN_STATUSES:
            return self.status
        if self.scheduled_at and (as_of or _utcnow()) > self.scheduled_at:
            return CRMWorkItemStatus.OVERDUE
        return self.status
