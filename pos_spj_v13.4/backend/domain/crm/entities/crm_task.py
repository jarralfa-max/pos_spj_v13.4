"""CRMTask — an actionable to-do with a deadline (§23-26). Named use cases
per the master prompt: CreateCRMTaskUseCase, CompleteCRMTaskUseCase,
RescheduleCRMTaskUseCase, AssignCRMTaskUseCase, CancelCRMTaskUseCase (see
backend/application/crm/use_cases/task_use_cases.py).

Status transitions:

    PLANNED ──complete()──► COMPLETED (terminal)
       │
       └──cancel(reason)──► CANCELLED (terminal)

    PLANNED ──reschedule(new_due_at)──► PLANNED

Unlike CRMActivity, a task has no IN_PROGRESS step in this phase's scope —
§23-26 doesn't describe a "start task" action, only create/complete/
reschedule/assign/cancel; adding one here would be a use case with no
caller. ``effective_status()`` reports OVERDUE without ever persisting it —
see CRMWorkItemStatus's docstring for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMRelatedEntityType, CRMWorkItemStatus
from backend.domain.crm.exceptions import InvalidCRMTaskStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_COMPLETABLE = {CRMWorkItemStatus.PLANNED}
_CANCELLABLE = {CRMWorkItemStatus.PLANNED}
_RESCHEDULABLE = {CRMWorkItemStatus.PLANNED}
_ASSIGNABLE = {CRMWorkItemStatus.PLANNED}
_OPEN_STATUSES = {CRMWorkItemStatus.PLANNED}


@dataclass(slots=True)
class CRMTask:
    id: str
    related_entity_type: CRMRelatedEntityType
    related_entity_id: str
    title: str
    due_at: str
    status: CRMWorkItemStatus = CRMWorkItemStatus.PLANNED
    assigned_user_id: str | None = None
    description: str = ""
    completed_at: str | None = None
    created_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, related_entity_type: CRMRelatedEntityType, related_entity_id: str, title: str,
        due_at: str, *, assigned_user_id: str | None = None, description: str = "",
        created_by_user_id: str | None = None, operation_id: str | None = None,
    ) -> "CRMTask":
        if not related_entity_id:
            raise InvalidCRMTaskStateError("related_entity_id es obligatorio")
        if not title or not title.strip():
            raise InvalidCRMTaskStateError("title es obligatorio")
        if not due_at:
            raise InvalidCRMTaskStateError("due_at es obligatorio")
        return cls(
            id=new_uuid(), related_entity_type=related_entity_type,
            related_entity_id=related_entity_id, title=title.strip(), due_at=due_at,
            assigned_user_id=assigned_user_id, description=description,
            created_by_user_id=created_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def complete(self) -> None:
        if self.status not in _COMPLETABLE:
            raise InvalidCRMTaskStateError(f"No se puede completar desde {self.status.value}")
        self.status = CRMWorkItemStatus.COMPLETED
        self.completed_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in _CANCELLABLE:
            raise InvalidCRMTaskStateError(f"No se puede cancelar desde {self.status.value}")
        if not reason.strip():
            raise InvalidCRMTaskStateError("Cancelar requiere un motivo")
        self.status = CRMWorkItemStatus.CANCELLED
        self._touch()

    def reschedule(self, new_due_at: str) -> None:
        if self.status not in _RESCHEDULABLE:
            raise InvalidCRMTaskStateError(f"No se puede reprogramar desde {self.status.value}")
        if not new_due_at:
            raise InvalidCRMTaskStateError("reschedule() requiere una nueva fecha límite")
        self.due_at = new_due_at
        self._touch()

    def assign(self, user_id: str) -> None:
        if self.status not in _ASSIGNABLE:
            raise InvalidCRMTaskStateError(f"No se puede asignar desde {self.status.value}")
        if not user_id:
            raise InvalidCRMTaskStateError("assign() requiere un usuario")
        self.assigned_user_id = user_id
        self._touch()

    def effective_status(self, *, as_of: str | None = None) -> CRMWorkItemStatus:
        if self.status not in _OPEN_STATUSES:
            return self.status
        if (as_of or _utcnow()) > self.due_at:
            return CRMWorkItemStatus.OVERDUE
        return self.status
