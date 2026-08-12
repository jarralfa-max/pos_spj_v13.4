"""CRMTask use cases — the five named explicitly in §23-26:
CreateCRMTaskUseCase, CompleteCRMTaskUseCase, RescheduleCRMTaskUseCase,
AssignCRMTaskUseCase, CancelCRMTaskUseCase.

Each: validates permission, runs in a CRMUnitOfWork, records audit and
enqueues the canonical event to the outbox. Idempotent on create
(operation_id).
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import CRMRelatedEntityType
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, task_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id, task_id=task_id,
                                      user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateCRMTaskUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, related_entity_type: str,
        related_entity_id: str, title: str, due_at: str, operation_id: str,
        assigned_user_id: str | None = None, description: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TASKS_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            existing = uow.tasks.get_by_operation_id(operation_id)
            if existing is not None:
                return CRMResult.ok("Tarea ya registrada", entity_id=existing.id,
                                    operation_id=operation_id)
            try:
                task = CRMTask.create(
                    CRMRelatedEntityType(related_entity_type), related_entity_id, title, due_at,
                    assigned_user_id=assigned_user_id, description=description,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tasks.save(task, operation_id=operation_id)
            uow.audit.record(action=CRMEvents.TASK_CREATED, actor_user_id=actor_user_id,
                             task_id=task.id, reason="alta", operation_id=operation_id)
            self._emit(uow, CRMEvents.TASK_CREATED, task.id, operation_id, actor_user_id)
        return CRMResult.ok("Tarea creada", entity_id=task.id, operation_id=operation_id)


class CompleteCRMTaskUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, task_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TASKS_COMPLETE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return CRMResult.fail("La tarea no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                task.complete()
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tasks.update(task)
            uow.audit.record(action=CRMEvents.TASK_COMPLETED, actor_user_id=actor_user_id,
                             task_id=task.id, operation_id=operation_id)
            self._emit(uow, CRMEvents.TASK_COMPLETED, task.id, operation_id, actor_user_id)
        return CRMResult.ok("Tarea completada", entity_id=task_id, operation_id=operation_id)


class CancelCRMTaskUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, task_id: str, operation_id: str,
                reason: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TASKS_CANCEL)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return CRMResult.fail("La tarea no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                task.cancel(reason)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tasks.update(task)
            uow.audit.record(action=CRMEvents.TASK_CANCELLED, actor_user_id=actor_user_id,
                             task_id=task.id, reason=reason, operation_id=operation_id)
            self._emit(uow, CRMEvents.TASK_CANCELLED, task.id, operation_id, actor_user_id)
        return CRMResult.ok("Tarea cancelada", entity_id=task_id, operation_id=operation_id)


class RescheduleCRMTaskUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, task_id: str, new_due_at: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.TASKS_RESCHEDULE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return CRMResult.fail("La tarea no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                task.reschedule(new_due_at)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tasks.update(task)
            uow.audit.record(action=CRMEvents.TASK_RESCHEDULED, actor_user_id=actor_user_id,
                             task_id=task.id, operation_id=operation_id)
            self._emit(uow, CRMEvents.TASK_RESCHEDULED, task.id, operation_id, actor_user_id,
                      new_due_at=new_due_at)
        return CRMResult.ok("Tarea reprogramada", entity_id=task_id, operation_id=operation_id)


class AssignCRMTaskUseCase(_BaseUseCase):
    """Requires TASKS_ASSIGN for the first assignment (no prior assignee)
    and TASKS_REASSIGN when handing an already-owned task to someone else —
    same pattern as AssignOpportunityUseCase (CRM-5), which itself closed a
    gap CRM-4's AssignLeadUseCase left open (see
    docs/refactor/CRM-5_oportunidades.md)."""

    def execute(self, connection, *, actor_user_id: str, task_id: str, assignee_user_id: str,
                operation_id: str) -> CRMResult:
        with CRMUnitOfWork(connection) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return CRMResult.fail("La tarea no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            permission = (CRMPermissions.TASKS_REASSIGN if task.assigned_user_id
                          else CRMPermissions.TASKS_ASSIGN)
            try:
                self._auth.require(actor_user_id, permission)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
            try:
                task.assign(assignee_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.tasks.update(task)
            event_name = (CRMEvents.TASK_REASSIGNED if permission == CRMPermissions.TASKS_REASSIGN
                          else CRMEvents.TASK_ASSIGNED)
            uow.audit.record(action=event_name, actor_user_id=actor_user_id, task_id=task.id,
                             operation_id=operation_id)
            self._emit(uow, event_name, task.id, operation_id, actor_user_id,
                      assignee_user_id=assignee_user_id)
        return CRMResult.ok("Tarea asignada", entity_id=task_id, operation_id=operation_id)
