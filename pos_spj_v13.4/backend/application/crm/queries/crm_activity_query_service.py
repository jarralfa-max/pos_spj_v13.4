"""CRMActivityQueryService (§57-style) — read side for Activities. Reads
only; never mutates.

Unlike LeadDirectoryQueryService/OpportunityDirectoryQueryService, this
does NOT use CRMDataScopeResolver — CRM-2's catalog only defines a flat
``ACTIVITIES_VIEW`` permission for this entity family (no ``ver.propia``/
``ver.equipo`` scope-suffixed pair, unlike leads/opportunities/cases). So
visibility here is gated by that one permission only; reaching a specific
activity in the UI is expected to flow through its parent entity's own
scoped query service first (e.g. you already had to pass
OpportunityDirectoryQueryService's OWN/TEAM check to be looking at that
opportunity's activity list at all).
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.enums import CRMWorkItemStatus
from backend.domain.crm.exceptions import CRMActivityNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CRMActivityQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def get(self, activity_id: str, *, actor_user_id: str) -> CRMActivity:
        self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_VIEW)
        activity = self._uow.activities.get(activity_id)
        if activity is None:
            raise CRMActivityNotFoundError(f"Actividad {activity_id!r} no existe")
        return activity

    def list_for_related_entity(self, related_entity_type: str, related_entity_id: str, *,
                                 actor_user_id: str) -> list[CRMActivity]:
        self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_VIEW)
        return self._uow.activities.list_for_related_entity(related_entity_type,
                                                              related_entity_id)

    def list_assigned_to(self, user_id: str, *, actor_user_id: str) -> list[CRMActivity]:
        self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_VIEW)
        return self._uow.activities.list_assigned_to(user_id)

    def list_overdue_for(self, user_id: str, *, actor_user_id: str,
                         as_of: str | None = None) -> list[CRMActivity]:
        """§23-26: "Vencida se muestra con estado+icono" — the query layer
        exposes overdue via ``effective_status()``, never a stored column."""
        self._auth.require(actor_user_id, CRMPermissions.ACTIVITIES_VIEW)
        return [a for a in self._uow.activities.list_assigned_to(user_id)
                if a.effective_status(as_of=as_of) is CRMWorkItemStatus.OVERDUE]
