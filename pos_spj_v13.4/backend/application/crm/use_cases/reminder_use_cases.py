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


#: Cuántos recordatorios entrega cada pasada; el resto sale en la siguiente.
REMINDER_DISPATCH_BATCH = 200


class DispatchDueCRMRemindersUseCase:
    """CRM-43: entrega en la bandeja personal (`notification_inbox`) los
    recordatorios del canal «En la aplicación» cuya hora ya llegó. Los demás
    canales no se ofrecen en la pantalla mientras no exista quien los envíe.

    Lo llama el ciclo de fondo del sistema (sin actor humano, como la
    evaluación de automatizaciones). Idempotente: marca ``delivered_at`` y la
    bandeja deduplica por recordatorio."""

    def execute(self, connection, *, now: str) -> int:
        from backend.infrastructure.notifications.in_app_inbox_repository import (
            InAppInboxRepository,
        )
        delivered = 0
        with CRMUnitOfWork(connection) as uow:
            inbox = InAppInboxRepository(connection)
            for reminder in uow.reminders.list_due(now, limit=REMINDER_DISPATCH_BATCH):
                about = ""
                if reminder.task_id:
                    task = uow.tasks.get(reminder.task_id)
                    about = f"Tarea: {task.title}" if task else ""
                elif reminder.activity_id:
                    activity = uow.activities.get(reminder.activity_id)
                    about = f"Actividad: {activity.subject}" if activity else ""
                body = "\n".join(part for part in (reminder.message, about) if part)
                inbox.deliver(
                    recipient_user_id=reminder.recipient_user_id, kind="CRM",
                    title="Recordatorio", body=body,
                    data={"reminder_id": reminder.id, "task_id": reminder.task_id,
                          "activity_id": reminder.activity_id},
                    dedupe_key=f"crm-reminder:{reminder.id}")
                uow.reminders.mark_delivered(reminder.id, now)
                delivered += 1
        return delivered
