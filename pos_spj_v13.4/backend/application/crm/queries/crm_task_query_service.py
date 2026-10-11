"""CRMTaskQueryService — read side for Tasks. Reads only; never mutates.
Auditoría CRM F03 (2026-10-09): además de ``TASKS_VIEW``, la visibilidad por
persona y por registro de ``WorkItemVisibility``.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.work_item_visibility import WorkItemVisibility
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import CRMWorkItemStatus
from backend.domain.crm.exceptions import CRMTaskNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CRMTaskQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None, *,
                 record_visible=None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()
        self._visibility = WorkItemVisibility(self._auth, CRMPermissions.TASKS_REASSIGN,
                                              record_visible)

    def get(self, task_id: str, *, actor_user_id: str) -> CRMTask:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        task = self._uow.tasks.get(task_id)
        if task is None or not self._visibility.can_see_item(
                actor_user_id, task, owners=(task.assigned_user_id, task.created_by_user_id)):
            raise CRMTaskNotFoundError(f"Tarea {task_id!r} no existe o está fuera de tu alcance")
        return task

    def list_for_related_entity(self, related_entity_type: str, related_entity_id: str, *,
                                 actor_user_id: str) -> list[CRMTask]:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        self._visibility.require_record(actor_user_id, related_entity_type, related_entity_id)
        return self._uow.tasks.list_for_related_entity(related_entity_type, related_entity_id)

    def list_assigned_to(self, user_id: str, *, actor_user_id: str) -> list[CRMTask]:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        self._visibility.require_user(actor_user_id, user_id)
        return self._uow.tasks.list_assigned_to(user_id)

    def list_overdue_for(self, user_id: str, *, actor_user_id: str,
                         as_of: str | None = None) -> list[CRMTask]:
        """§23-26: "Vencida se muestra con estado+icono" — the query layer
        exposes overdue via ``effective_status()``, never a stored column."""
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        self._visibility.require_user(actor_user_id, user_id)
        return [t for t in self._uow.tasks.list_assigned_to(user_id)
                if t.effective_status(as_of=as_of) is CRMWorkItemStatus.OVERDUE]
