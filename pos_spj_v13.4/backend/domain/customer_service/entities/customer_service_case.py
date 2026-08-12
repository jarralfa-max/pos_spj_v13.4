"""CustomerServiceCase — the CRM-7 aggregate root (§30-32).

Status transitions:

    NEW ──assign_owner()──► ASSIGNED ──start_progress()──► IN_PROGRESS
                                              │  ▲
                    wait_for_customer()/wait_internal()  resume()
                                              ▼  │
                              WAITING_CUSTOMER / WAITING_INTERNAL

    {ASSIGNED,IN_PROGRESS,WAITING_*} ──escalate(...)──► ESCALATED (re-escalatable)
    {ASSIGNED,IN_PROGRESS,WAITING_*,ESCALATED} ──resolve()──► RESOLVED ──close()──► CLOSED
    {NEW,ASSIGNED,IN_PROGRESS,WAITING_*,ESCALATED} ──cancel(reason)──► CANCELLED
    {RESOLVED,CLOSED} ──reopen(reason)──► IN_PROGRESS (reopen_count += 1)

``escalation_level`` is NOT tracked here — it lives on ``SLAInstance``
(§30-32 lists it as an SLAInstance field, and duplicating it on the case
would just invite the two counters drifting). ``resolve()``/``close()``
only flip status — the actual resolution detail is a separate
``ServiceCaseResolution`` row (mirrors ``Lead.qualify()`` vs.
``LeadQualification``) and each escalation is a separate immutable
``ServiceCaseEscalation`` row (mirrors ``OpportunityStageHistory``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseStatus,
    ServiceCaseType,
)
from backend.domain.customer_service.exceptions import InvalidServiceCaseStateError
from backend.domain.customer_service.value_objects.service_case_code import ServiceCaseCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_ASSIGNABLE = {ServiceCaseStatus.NEW, ServiceCaseStatus.ASSIGNED, ServiceCaseStatus.IN_PROGRESS,
               ServiceCaseStatus.WAITING_CUSTOMER, ServiceCaseStatus.WAITING_INTERNAL,
               ServiceCaseStatus.ESCALATED}
_STARTABLE = {ServiceCaseStatus.ASSIGNED}
_WAITABLE = {ServiceCaseStatus.IN_PROGRESS, ServiceCaseStatus.ESCALATED}
_RESUMABLE = {ServiceCaseStatus.WAITING_CUSTOMER, ServiceCaseStatus.WAITING_INTERNAL}
_ESCALATABLE = {ServiceCaseStatus.NEW, ServiceCaseStatus.ASSIGNED, ServiceCaseStatus.IN_PROGRESS,
                ServiceCaseStatus.WAITING_CUSTOMER, ServiceCaseStatus.WAITING_INTERNAL,
                ServiceCaseStatus.ESCALATED}
_RESOLVABLE = {ServiceCaseStatus.ASSIGNED, ServiceCaseStatus.IN_PROGRESS,
               ServiceCaseStatus.WAITING_CUSTOMER, ServiceCaseStatus.WAITING_INTERNAL,
               ServiceCaseStatus.ESCALATED}
_CLOSABLE = {ServiceCaseStatus.RESOLVED}
_CANCELLABLE = {ServiceCaseStatus.NEW, ServiceCaseStatus.ASSIGNED, ServiceCaseStatus.IN_PROGRESS,
                ServiceCaseStatus.WAITING_CUSTOMER, ServiceCaseStatus.WAITING_INTERNAL,
                ServiceCaseStatus.ESCALATED}
_REOPENABLE = {ServiceCaseStatus.RESOLVED, ServiceCaseStatus.CLOSED}
_TERMINAL = {ServiceCaseStatus.CLOSED, ServiceCaseStatus.CANCELLED}


@dataclass(slots=True)
class CustomerServiceCase:
    id: str
    code: ServiceCaseCode
    customer_id: str
    case_type: ServiceCaseType
    subject: str
    status: ServiceCaseStatus = ServiceCaseStatus.NEW
    priority: ServiceCasePriority = ServiceCasePriority.NORMAL
    category_id: str | None = None
    description: str = ""
    assigned_user_id: str | None = None
    channel: ServiceCaseChannel = ServiceCaseChannel.OTHER
    origin_branch_id: str | None = None
    territory_id: str | None = None
    is_sensitive: bool = False
    reopen_count: int = 0
    close_reason: str = ""
    resolved_at: str | None = None
    closed_at: str | None = None
    created_by_user_id: str | None = None
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: ServiceCaseCode, customer_id: str, case_type: ServiceCaseType, subject: str, *,
        priority: ServiceCasePriority = ServiceCasePriority.NORMAL, category_id: str | None = None,
        description: str = "", channel: ServiceCaseChannel = ServiceCaseChannel.OTHER,
        origin_branch_id: str | None = None, territory_id: str | None = None,
        is_sensitive: bool = False, created_by_user_id: str | None = None,
        operation_id: str | None = None,
    ) -> "CustomerServiceCase":
        if not customer_id:
            raise InvalidServiceCaseStateError("customer_id es obligatorio")
        if not subject or not subject.strip():
            raise InvalidServiceCaseStateError("subject es obligatorio")
        return cls(
            id=new_uuid(), code=code, customer_id=customer_id, case_type=case_type,
            subject=subject.strip(), priority=priority, category_id=category_id,
            description=description, channel=channel, origin_branch_id=origin_branch_id,
            territory_id=territory_id, is_sensitive=is_sensitive,
            created_by_user_id=created_by_user_id, operation_id=operation_id,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # lifecycle ---------------------------------------------------------------
    def assign_owner(self, user_id: str) -> None:
        if self.status not in _ASSIGNABLE:
            raise InvalidServiceCaseStateError(
                f"No se puede asignar propietario desde {self.status.value}")
        if not user_id:
            raise InvalidServiceCaseStateError("assign_owner() requiere un usuario")
        self.assigned_user_id = user_id
        if self.status is ServiceCaseStatus.NEW:
            self.status = ServiceCaseStatus.ASSIGNED
        self._touch()

    def start_progress(self) -> None:
        if self.status not in _STARTABLE:
            raise InvalidServiceCaseStateError(f"No se puede iniciar desde {self.status.value}")
        self.status = ServiceCaseStatus.IN_PROGRESS
        self._touch()

    def wait_for_customer(self) -> None:
        if self.status not in _WAITABLE:
            raise InvalidServiceCaseStateError(
                f"No se puede poner en espera del cliente desde {self.status.value}")
        self.status = ServiceCaseStatus.WAITING_CUSTOMER
        self._touch()

    def wait_internal(self) -> None:
        if self.status not in _WAITABLE:
            raise InvalidServiceCaseStateError(
                f"No se puede poner en espera interna desde {self.status.value}")
        self.status = ServiceCaseStatus.WAITING_INTERNAL
        self._touch()

    def resume(self) -> None:
        if self.status not in _RESUMABLE:
            raise InvalidServiceCaseStateError(f"No se puede reanudar desde {self.status.value}")
        self.status = ServiceCaseStatus.IN_PROGRESS
        self._touch()

    def escalate(self) -> None:
        if self.status not in _ESCALATABLE:
            raise InvalidServiceCaseStateError(f"No se puede escalar desde {self.status.value}")
        self.status = ServiceCaseStatus.ESCALATED
        self._touch()

    def resolve(self) -> None:
        if self.status not in _RESOLVABLE:
            raise InvalidServiceCaseStateError(f"No se puede resolver desde {self.status.value}")
        self.status = ServiceCaseStatus.RESOLVED
        self.resolved_at = _utcnow()
        self._touch()

    def close(self) -> None:
        if self.status not in _CLOSABLE:
            raise InvalidServiceCaseStateError(f"No se puede cerrar desde {self.status.value}")
        self.status = ServiceCaseStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def cancel(self, reason: str) -> None:
        if self.status not in _CANCELLABLE:
            raise InvalidServiceCaseStateError(f"No se puede cancelar desde {self.status.value}")
        if not reason.strip():
            raise InvalidServiceCaseStateError("Cancelar requiere un motivo")
        self.status = ServiceCaseStatus.CANCELLED
        self.close_reason = reason
        self.closed_at = _utcnow()
        self._touch()

    def reopen(self, reason: str) -> None:
        if self.status not in _REOPENABLE:
            raise InvalidServiceCaseStateError(f"No se puede reabrir desde {self.status.value}")
        if not reason.strip():
            raise InvalidServiceCaseStateError("Reabrir requiere un motivo")
        self.status = ServiceCaseStatus.IN_PROGRESS
        self.reopen_count += 1
        self.resolved_at = None
        self.closed_at = None
        self.close_reason = ""
        self._touch()

    def record_edit(self) -> None:
        self._touch()

    # capability checks -------------------------------------------------------
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    def is_open(self) -> bool:
        return self.status not in _TERMINAL
