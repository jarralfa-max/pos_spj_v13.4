"""CRMReminderRepository — persists the CRMReminder entity."""

from __future__ import annotations

from backend.domain.crm.entities.crm_reminder import CRMReminder
from backend.domain.crm.enums import ReminderChannel
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_REMINDER_COLS = (
    "id, channel, remind_at, recipient_user_id, task_id, activity_id,"
    " message, created_by_user_id, created_at"
)


class CRMReminderRepository(CRMRepositoryBase):
    def save(self, reminder: CRMReminder) -> None:
        self._execute(
            f"INSERT INTO crm_reminders ({_REMINDER_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
            (reminder.id, reminder.channel.value, reminder.remind_at,
             reminder.recipient_user_id, reminder.task_id, reminder.activity_id,
             reminder.message, reminder.created_by_user_id, reminder.created_at))

    def list_for_task(self, task_id: str) -> list[CRMReminder]:
        rows = self._query(
            f"SELECT {_REMINDER_COLS} FROM crm_reminders WHERE task_id=? ORDER BY remind_at ASC",
            (task_id,))
        return [self._hydrate(r) for r in rows]

    def list_due(self, now: str, *, limit: int) -> list[CRMReminder]:
        """CRM-43: los recordatorios en la bandeja cuya hora ya llegó y que aún no
        se entregan (migración 317)."""
        rows = self._query(
            f"SELECT {_REMINDER_COLS} FROM crm_reminders"
            " WHERE delivered_at IS NULL AND channel='IN_APP' AND remind_at <= ?"
            " ORDER BY remind_at ASC LIMIT ?", (now, limit))
        return [self._hydrate(r) for r in rows]

    def mark_delivered(self, reminder_id: str, delivered_at: str) -> None:
        self._execute("UPDATE crm_reminders SET delivered_at=? WHERE id=? AND delivered_at IS NULL",
                      (delivered_at, reminder_id))

    def list_for_activity(self, activity_id: str) -> list[CRMReminder]:
        rows = self._query(
            f"SELECT {_REMINDER_COLS} FROM crm_reminders"
            " WHERE activity_id=? ORDER BY remind_at ASC", (activity_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> CRMReminder:
        return CRMReminder(
            id=row["id"], channel=ReminderChannel(row["channel"]), remind_at=row["remind_at"],
            recipient_user_id=row["recipient_user_id"], task_id=row["task_id"],
            activity_id=row["activity_id"], message=row["message"] or "",
            created_by_user_id=row["created_by_user_id"], created_at=row["created_at"],
        )
