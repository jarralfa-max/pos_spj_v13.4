"""Canonical CRM domain events (§77) — names + payload builder. Mirrors
backend/domain/customers/events.py. The Leads subset landed in CRM-4,
Opportunities/pipeline in CRM-5, Activities/Tasks/Notes/Reminders here in
CRM-6. Service Case events are added when CRM-7 builds that entity.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CRMEvents:
    LEAD_CREATED = "CRM_LEAD_CREATED"
    LEAD_ASSIGNED = "CRM_LEAD_ASSIGNED"
    LEAD_CONTACTED = "CRM_LEAD_CONTACTED"
    LEAD_NURTURING = "CRM_LEAD_NURTURING"
    LEAD_QUALIFIED = "CRM_LEAD_QUALIFIED"
    LEAD_DISQUALIFIED = "CRM_LEAD_DISQUALIFIED"
    LEAD_CONVERTED = "CRM_LEAD_CONVERTED"
    LEAD_LOST = "CRM_LEAD_LOST"
    LEAD_ARCHIVED = "CRM_LEAD_ARCHIVED"
    LEAD_UPDATED = "CRM_LEAD_UPDATED"

    OPPORTUNITY_CREATED = "CRM_OPPORTUNITY_CREATED"
    OPPORTUNITY_UPDATED = "CRM_OPPORTUNITY_UPDATED"
    OPPORTUNITY_ASSIGNED = "CRM_OPPORTUNITY_ASSIGNED"
    OPPORTUNITY_STAGE_CHANGED = "CRM_OPPORTUNITY_STAGE_CHANGED"
    OPPORTUNITY_PUT_ON_HOLD = "CRM_OPPORTUNITY_PUT_ON_HOLD"
    OPPORTUNITY_RESUMED = "CRM_OPPORTUNITY_RESUMED"
    OPPORTUNITY_WON = "CRM_OPPORTUNITY_WON"
    OPPORTUNITY_LOST = "CRM_OPPORTUNITY_LOST"
    OPPORTUNITY_CANCELLED = "CRM_OPPORTUNITY_CANCELLED"
    OPPORTUNITY_REOPENED = "CRM_OPPORTUNITY_REOPENED"

    ACTIVITY_CREATED = "CRM_ACTIVITY_CREATED"
    ACTIVITY_STARTED = "CRM_ACTIVITY_STARTED"
    ACTIVITY_COMPLETED = "CRM_ACTIVITY_COMPLETED"
    ACTIVITY_CANCELLED = "CRM_ACTIVITY_CANCELLED"
    ACTIVITY_RESCHEDULED = "CRM_ACTIVITY_RESCHEDULED"
    ACTIVITY_REASSIGNED = "CRM_ACTIVITY_REASSIGNED"

    TASK_CREATED = "CRM_TASK_CREATED"
    TASK_ASSIGNED = "CRM_TASK_ASSIGNED"
    TASK_REASSIGNED = "CRM_TASK_REASSIGNED"
    TASK_COMPLETED = "CRM_TASK_COMPLETED"
    TASK_CANCELLED = "CRM_TASK_CANCELLED"
    TASK_RESCHEDULED = "CRM_TASK_RESCHEDULED"

    NOTE_CREATED = "CRM_NOTE_CREATED"
    NOTE_UPDATED = "CRM_NOTE_UPDATED"
    NOTE_DELETED = "CRM_NOTE_DELETED"

    REMINDER_CREATED = "CRM_REMINDER_CREATED"


ALL_CRM_EVENTS = frozenset(
    v for k, v in vars(CRMEvents).items() if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, lead_id: str | None = None,
                        opportunity_id: str | None = None, user_id: str | None = None,
                        branch_id: str | None = None, source_module: str = "crm",
                        **extra) -> dict:
    """Build the canonical minimum payload for a CRM event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "lead_id": lead_id,
        "opportunity_id": opportunity_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload
