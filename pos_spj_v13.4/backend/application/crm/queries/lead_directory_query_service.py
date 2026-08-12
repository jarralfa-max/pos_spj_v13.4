"""LeadDirectoryQueryService (§57) — read side for Leads. Reads only; never
mutates. First real consumer of CRM-2's ``CRMDataScopeResolver`` for the
Leads entity family (OWN/TEAM axes — see
backend/application/crm/data_scope.py for why Leads has no BRANCH/
TERRITORY/PORTFOLIO/COMPANY axes of its own).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import LEAD_VIEW_SCOPE_PERMISSIONS
from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.exceptions import CRMScopeError, LeadNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class LeadProfile:
    lead: Lead
    qualifications: list[LeadQualification] = field(default_factory=list)


class LeadDirectoryQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._scope_resolver = scope_resolver

    def get_profile(self, lead_id: str, context: CRMScopeContext) -> LeadProfile:
        scope = self._scope_resolver.resolve_view_scope(context, LEAD_VIEW_SCOPE_PERMISSIONS)
        lead = self._uow.leads.get(lead_id)
        if lead is None:
            raise LeadNotFoundError(f"Lead {lead_id!r} no existe")
        if not self._in_scope(lead, scope):
            raise CRMScopeError(
                f"El lead {lead_id!r} está fuera del alcance ({scope.axis}) del usuario")
        return LeadProfile(lead=lead, qualifications=self._uow.qualifications.list_for_lead(lead_id))

    def list_directory(self, context: CRMScopeContext, *, limit: int = 200,
                        offset: int = 0) -> list[Lead]:
        scope = self._scope_resolver.resolve_view_scope(context, LEAD_VIEW_SCOPE_PERMISSIONS)
        owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
        return self._uow.leads.list_owned_by(owner_ids, limit=limit, offset=offset)

    @staticmethod
    def _in_scope(lead: Lead, scope: CRMDataScope) -> bool:
        if scope.axis == "OWN":
            return lead.assigned_user_id == scope.owner_user_id
        return lead.assigned_user_id in scope.team_member_ids
