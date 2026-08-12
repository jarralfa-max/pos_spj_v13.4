"""CRMActivityRepository — persists the CRMActivity entity. Mirrors
backend/infrastructure/db/repositories/crm/lead_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType, CRMWorkItemStatus
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_ACTIVITY_COLS = (
    "id, activity_type, related_entity_type, related_entity_id, subject,"
    " status, scheduled_at, completed_at, assigned_user_id, description,"
    " created_by_user_id, operation_id, created_at, updated_at"
)


class CRMActivityRepository(CRMRepositoryBase):
    def save(self, activity: CRMActivity, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO crm_activities ({_ACTIVITY_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(activity, operation_id or activity.operation_id))

    def update(self, activity: CRMActivity) -> None:
        self._execute(
            "UPDATE crm_activities SET subject=?, status=?, scheduled_at=?, completed_at=?,"
            " assigned_user_id=?, description=?, updated_at=? WHERE id=?",
            (activity.subject, activity.status.value, activity.scheduled_at,
             activity.completed_at, activity.assigned_user_id, activity.description,
             activity.updated_at, activity.id))

    def get(self, activity_id: str) -> CRMActivity | None:
        row = self._query_one(f"SELECT {_ACTIVITY_COLS} FROM crm_activities WHERE id=?",
                              (activity_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CRMActivity | None:
        row = self._query_one(
            f"SELECT {_ACTIVITY_COLS} FROM crm_activities WHERE operation_id=?",
            (operation_id,))
        return self._hydrate(row) if row else None

    def list_for_related_entity(self, related_entity_type: str,
                                 related_entity_id: str) -> list[CRMActivity]:
        rows = self._query(
            f"SELECT {_ACTIVITY_COLS} FROM crm_activities"
            " WHERE related_entity_type=? AND related_entity_id=? ORDER BY created_at DESC",
            (related_entity_type, related_entity_id))
        return [self._hydrate(r) for r in rows]

    def list_assigned_to(self, user_id: str) -> list[CRMActivity]:
        rows = self._query(
            f"SELECT {_ACTIVITY_COLS} FROM crm_activities"
            " WHERE assigned_user_id=? ORDER BY created_at DESC", (user_id,))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(activity: CRMActivity, operation_id: str | None) -> tuple:
        return (
            activity.id, activity.activity_type.value, activity.related_entity_type.value,
            activity.related_entity_id, activity.subject, activity.status.value,
            activity.scheduled_at, activity.completed_at, activity.assigned_user_id,
            activity.description, activity.created_by_user_id, operation_id,
            activity.created_at, activity.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMActivity:
        return CRMActivity(
            id=row["id"], activity_type=CRMActivityType(row["activity_type"]),
            related_entity_type=CRMRelatedEntityType(row["related_entity_type"]),
            related_entity_id=row["related_entity_id"], subject=row["subject"],
            status=CRMWorkItemStatus(row["status"]), scheduled_at=row["scheduled_at"],
            completed_at=row["completed_at"], assigned_user_id=row["assigned_user_id"],
            description=row["description"] or "", created_by_user_id=row["created_by_user_id"],
            operation_id=row["operation_id"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
