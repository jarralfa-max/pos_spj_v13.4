"""CRMCalendarQueryService (§57) — combined calendar view over Activities
and Tasks for one user, filtered to a date range. Reads only; never
mutates. Reminders are deliberately excluded: a CRMReminder has no
independent "when it's due" beyond the task/activity it's attached to, so
surfacing the task/activity itself is enough for a calendar — reminders
are a delivery mechanism (§26: "CRM solo define recordatorio/destinatario"),
not a second calendar-worthy occurrence.

Flat ACTIVITIES_VIEW/TASKS_VIEW permissions, same no-scope-suffix
precedent as CRMActivityQueryService/CRMTaskQueryService (this entity
family has no ``ver.propia``/``ver.equipo`` pair in the catalog).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class CRMCalendarEntry:
    entry_type: str  # ACTIVITY | TASK
    entity_id: str
    title: str
    when: str
    status: str


class CRMCalendarQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get_calendar(
        self, user_id: str, *, actor_user_id: str, start_date: str, end_date: str,
    ) -> list[CRMCalendarEntry]:
        """``start_date``/``end_date`` are inclusive ISO dates (YYYY-MM-DD),
        compared against the leading 10 characters of each item's
        scheduled_at/due_at timestamp."""
        self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_VIEW)
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)

        entries: list[CRMCalendarEntry] = []
        for activity in self._uow.activities.list_assigned_to(user_id):
            if activity.scheduled_at and start_date <= activity.scheduled_at[:10] <= end_date:
                entries.append(CRMCalendarEntry(
                    entry_type="ACTIVITY", entity_id=activity.id, title=activity.subject,
                    when=activity.scheduled_at, status=activity.status.value))
        for task in self._uow.tasks.list_assigned_to(user_id):
            if task.due_at and start_date <= task.due_at[:10] <= end_date:
                entries.append(CRMCalendarEntry(
                    entry_type="TASK", entity_id=task.id, title=task.title,
                    when=task.due_at, status=task.status.value))
        entries.sort(key=lambda e: e.when)
        return entries
