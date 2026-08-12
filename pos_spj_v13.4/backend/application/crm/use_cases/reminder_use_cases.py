"""CRMReminder use cases: create only.

§23-26: "CRM solo define recordatorio/destinatario" — no update/delete/
dispatch lifecycle here; sending is Notification Management's job, and
CRM-6 doesn't invent a reminder lifecycle the master prompt never
described.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.crm_reminder import CRMReminder
from backend.domain.crm.enums import ReminderChannel
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CreateCRMReminderUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, channel: str, remind_at: str,
        recipient_user_id: str, operation_id: str, task_id: str | None = None,
        activity_id: str | None = None, message: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.REMINDERS_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if task_id is not None and uow.tasks.get(task_id) is None:
                return CRMResult.fail("La tarea no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if activity_id is not None and uow.activities.get(activity_id) is None:
                return CRMResult.fail("La actividad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                reminder = CRMReminder.create(
                    ReminderChannel(channel), remind_at, recipient_user_id, task_id=task_id,
                    activity_id=activity_id, message=message, created_by_user_id=actor_user_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.reminders.save(reminder)
            payload = build_event_payload(
                CRMEvents.REMINDER_CREATED, operation_id=operation_id, user_id=actor_user_id,
                reminder_id=reminder.id, task_id=task_id, activity_id=activity_id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.REMINDER_CREATED,
                               json.dumps(payload), operation_id)
        return CRMResult.ok("Recordatorio creado", entity_id=reminder.id,
                            operation_id=operation_id)
