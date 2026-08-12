"""CRMTaskRepository — persists the CRMTask entity. Mirrors
backend/infrastructure/db/repositories/crm/lead_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import CRMRelatedEntityType, CRMWorkItemStatus
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_TASK_COLS = (
    "id, related_entity_type, related_entity_id, title, due_at, status,"
    " assigned_user_id, description, completed_at, created_by_user_id,"
    " operation_id, created_at, updated_at"
)


class CRMTaskRepository(CRMRepositoryBase):
    def save(self, task: CRMTask, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO crm_tasks ({_TASK_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(task, operation_id or task.operation_id))

    def update(self, task: CRMTask) -> None:
        self._execute(
            "UPDATE crm_tasks SET title=?, due_at=?, status=?, assigned_user_id=?,"
            " description=?, completed_at=?, updated_at=? WHERE id=?",
            (task.title, task.due_at, task.status.value, task.assigned_user_id,
             task.description, task.completed_at, task.updated_at, task.id))

    def get(self, task_id: str) -> CRMTask | None:
        row = self._query_one(f"SELECT {_TASK_COLS} FROM crm_tasks WHERE id=?", (task_id,))
        return self._hydrate(row) if row else None

    def get_by_operation_id(self, operation_id: str) -> CRMTask | None:
        row = self._query_one(
            f"SELECT {_TASK_COLS} FROM crm_tasks WHERE operation_id=?", (operation_id,))
        return self._hydrate(row) if row else None

    def list_for_related_entity(self, related_entity_type: str,
                                 related_entity_id: str) -> list[CRMTask]:
        rows = self._query(
            f"SELECT {_TASK_COLS} FROM crm_tasks"
            " WHERE related_entity_type=? AND related_entity_id=? ORDER BY due_at ASC",
            (related_entity_type, related_entity_id))
        return [self._hydrate(r) for r in rows]

    def list_assigned_to(self, user_id: str) -> list[CRMTask]:
        rows = self._query(
            f"SELECT {_TASK_COLS} FROM crm_tasks WHERE assigned_user_id=? ORDER BY due_at ASC",
            (user_id,))
        return [self._hydrate(r) for r in rows]

    def list_open(self, *, limit: int = 500, offset: int = 0) -> list[CRMTask]:
        rows = self._query(
            f"SELECT {_TASK_COLS} FROM crm_tasks WHERE status='PLANNED'"
            " ORDER BY due_at ASC LIMIT ? OFFSET ?", (limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(task: CRMTask, operation_id: str | None) -> tuple:
        return (
            task.id, task.related_entity_type.value, task.related_entity_id, task.title,
            task.due_at, task.status.value, task.assigned_user_id, task.description,
            task.completed_at, task.created_by_user_id, operation_id, task.created_at,
            task.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CRMTask:
        return CRMTask(
            id=row["id"], related_entity_type=CRMRelatedEntityType(row["related_entity_type"]),
            related_entity_id=row["related_entity_id"], title=row["title"], due_at=row["due_at"],
            status=CRMWorkItemStatus(row["status"]), assigned_user_id=row["assigned_user_id"],
            description=row["description"] or "", completed_at=row["completed_at"],
            created_by_user_id=row["created_by_user_id"], operation_id=row["operation_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
