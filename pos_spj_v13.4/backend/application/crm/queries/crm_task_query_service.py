"""CRMTaskQueryService — read side for Tasks. Reads only; never mutates.
Same flat-permission model as CRMActivityQueryService (only
``TASKS_VIEW``, no OWN/TEAM scope axis) — see that service's docstring.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import CRMWorkItemStatus
from backend.domain.crm.exceptions import CRMTaskNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CRMTaskQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get(self, task_id: str, *, actor_user_id: str) -> CRMTask:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        task = self._uow.tasks.get(task_id)
        if task is None:
            raise CRMTaskNotFoundError(f"Tarea {task_id!r} no existe")
        return task

    def list_for_related_entity(self, related_entity_type: str, related_entity_id: str, *,
                                 actor_user_id: str) -> list[CRMTask]:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        return self._uow.tasks.list_for_related_entity(related_entity_type, related_entity_id)

    def list_assigned_to(self, user_id: str, *, actor_user_id: str) -> list[CRMTask]:
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        return self._uow.tasks.list_assigned_to(user_id)

    def list_overdue_for(self, user_id: str, *, actor_user_id: str,
                         as_of: str | None = None) -> list[CRMTask]:
        """§23-26: "Vencida se muestra con estado+icono" — the query layer
        exposes overdue via ``effective_status()``, never a stored column."""
        self._auth.require(actor_user_id, CRMPermissions.TASKS_VIEW)
        return [t for t in self._uow.tasks.list_assigned_to(user_id)
                if t.effective_status(as_of=as_of) is CRMWorkItemStatus.OVERDUE]
