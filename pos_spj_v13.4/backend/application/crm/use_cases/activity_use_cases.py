"""CRMActivity use cases: create, start, complete, cancel, reschedule,
reassign.

Each: validates permission, runs in a CRMUnitOfWork, records audit and
enqueues the canonical event to the outbox. Idempotent on create
(operation_id). Mirrors
backend/application/crm/use_cases/lead_use_cases.py.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, activity_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      activity_id=activity_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateCRMActivityUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, activity_type: str,
        related_entity_type: str, related_entity_id: str, subject: str, operation_id: str,
        scheduled_at: str | None = None, assigned_user_id: str | None = None,
        description: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            existing = uow.activities.get_by_operation_id(operation_id)
            if existing is not None:
                return CRMResult.ok("Actividad ya registrada", entity_id=existing.id,
                                    operation_id=operation_id)
            try:
                activity = CRMActivity.create(
                    CRMActivityType(activity_type), CRMRelatedEntityType(related_entity_type),
                    related_entity_id, subject, scheduled_at=scheduled_at,
                    assigned_user_id=assigned_user_id, description=description,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.activities.save(activity, operation_id=operation_id)
            uow.audit.record(action=CRMEvents.ACTIVITY_CREATED, actor_user_id=actor_user_id,
                             activity_id=activity.id, reason="alta", operation_id=operation_id)
            self._emit(uow, CRMEvents.ACTIVITY_CREATED, activity.id, operation_id, actor_user_id)
        return CRMResult.ok("Actividad creada", entity_id=activity.id, operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, activity: CRMActivity, *, actor_user_id: str, reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, activity_id: str,
                operation_id: str, reason: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            activity = uow.activities.get(activity_id)
            if activity is None:
                return CRMResult.fail("La actividad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                self._apply(activity, actor_user_id=actor_user_id, reason=reason)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.activities.update(activity)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             activity_id=activity.id, reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, activity.id, operation_id, actor_user_id)
        return CRMResult.ok("Operación registrada", entity_id=activity_id,
                            operation_id=operation_id)


class StartCRMActivityUseCase(_TransitionUseCase):
    permission = CRMPermissions.ACTIVITIES_EDIT
    event_name = CRMEvents.ACTIVITY_STARTED

    def _apply(self, activity, *, actor_user_id, reason):
        activity.start()


class CompleteCRMActivityUseCase(_TransitionUseCase):
    permission = CRMPermissions.ACTIVITIES_COMPLETE
    event_name = CRMEvents.ACTIVITY_COMPLETED

    def _apply(self, activity, *, actor_user_id, reason):
        activity.complete()


class CancelCRMActivityUseCase(_TransitionUseCase):
    permission = CRMPermissions.ACTIVITIES_CANCEL
    event_name = CRMEvents.ACTIVITY_CANCELLED

    def _apply(self, activity, *, actor_user_id, reason):
        activity.cancel(reason)


class RescheduleCRMActivityUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, activity_id: str,
                new_scheduled_at: str, operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            activity = uow.activities.get(activity_id)
            if activity is None:
                return CRMResult.fail("La actividad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                activity.reschedule(new_scheduled_at)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.activities.update(activity)
            uow.audit.record(action=CRMEvents.ACTIVITY_RESCHEDULED, actor_user_id=actor_user_id,
                             activity_id=activity.id, operation_id=operation_id)
            self._emit(uow, CRMEvents.ACTIVITY_RESCHEDULED, activity.id, operation_id,
                      actor_user_id, new_scheduled_at=new_scheduled_at)
        return CRMResult.ok("Actividad reprogramada", entity_id=activity_id,
                            operation_id=operation_id)


class ReassignCRMActivityUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, activity_id: str,
                assignee_user_id: str, operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_REASSIGN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            activity = uow.activities.get(activity_id)
            if activity is None:
                return CRMResult.fail("La actividad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                activity.reassign(assignee_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.activities.update(activity)
            uow.audit.record(action=CRMEvents.ACTIVITY_REASSIGNED, actor_user_id=actor_user_id,
                             activity_id=activity.id, operation_id=operation_id)
            self._emit(uow, CRMEvents.ACTIVITY_REASSIGNED, activity.id, operation_id,
                      actor_user_id, assignee_user_id=assignee_user_id)
        return CRMResult.ok("Actividad reasignada", entity_id=activity_id,
                            operation_id=operation_id)
