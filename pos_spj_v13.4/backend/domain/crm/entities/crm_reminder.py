"""CRMReminder — "CRM solo define recordatorio/destinatario" (§23-26):
CRM's job stops at recording *what* should be reminded, *when*, on *which
channel*, and *to whom*. Sending is Notification Management's job, never
triggered "desde widgets" (from ad-hoc UI code) — so this entity has no
`mark_sent()`/dispatch status; that lifecycle belongs to whatever consumes
this record, not to CRM.

Always attached to a CRMTask or a CRMActivity (never a bare lead/
opportunity) — "remind me about this call" / "remind me this task is due"
are the two real use cases §23-26 describes; a free-floating reminder with
no work item behind it isn't one of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import ReminderChannel
from backend.domain.crm.exceptions import InvalidCRMReminderError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMReminder:
    id: str
    channel: ReminderChannel
    remind_at: str
    recipient_user_id: str
    task_id: str | None = None
    activity_id: str | None = None
    message: str = ""
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, channel: ReminderChannel, remind_at: str, recipient_user_id: str, *,
        task_id: str | None = None, activity_id: str | None = None, message: str = "",
        created_by_user_id: str | None = None,
    ) -> "CRMReminder":
        if not remind_at:
            raise InvalidCRMReminderError("remind_at es obligatorio")
        if not recipient_user_id:
            raise InvalidCRMReminderError("recipient_user_id es obligatorio")
        if not task_id and not activity_id:
            raise InvalidCRMReminderError(
                "Un recordatorio debe asociarse a una tarea o a una actividad")
        if task_id and activity_id:
            raise InvalidCRMReminderError(
                "Un recordatorio no puede asociarse a una tarea y una actividad a la vez")
        return cls(
            id=new_uuid(), channel=channel, remind_at=remind_at,
            recipient_user_id=recipient_user_id, task_id=task_id, activity_id=activity_id,
            message=message, created_by_user_id=created_by_user_id,
        )
