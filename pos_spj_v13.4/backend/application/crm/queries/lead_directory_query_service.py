"""LeadDirectoryQueryService (§57) — read side for Leads. Reads only; never
mutates. First real consumer of CRM-2's ``CRMDataScopeResolver`` for the
Leads entity family (OWN/TEAM axes — see
backend/application/crm/data_scope.py for why Leads has no BRANCH/
TERRITORY/PORTFOLIO/COMPANY axes of its own).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CRMPermissions, LEAD_VIEW_SCOPE_PERMISSIONS
from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.enums import LeadStatus
from backend.domain.crm.exceptions import CRMScopeError, LeadNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class LeadProfile:
    lead: Lead
    qualifications: list[LeadQualification] = field(default_factory=list)


class LeadDirectoryQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver,
                 authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._scope_resolver = scope_resolver
        self._auth = authorization or CRMAuthorizationPolicy()

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

    def count_new(self, *, actor_user_id: str) -> int:
        """CRM-15 (§90 dashboard KPI "Leads nuevos"): a NEW lead is by
        definition unassigned (``assigned_user_id`` is only ever set by
        ``AssignLeadUseCase``, which also advances the status past NEW) —
        so it can never appear in anyone's OWN/TEAM-scoped
        ``list_directory()``. "Leads nuevos" is inherently a shared triage
        queue, not a personal one, so this is the one deliberately
        UNSCOPED read in this service — same reasoning CRM-12's
        ``CustomerLookupQueryService`` already used for its own one
        unscoped query. Reuses ``list_open()`` (built alongside
        ``list_owned_by()`` from day one, never consumed until now) rather
        than adding a new repository method."""
        self._auth.require(actor_user_id, CRMPermissions.LEADS_VIEW)
        return sum(1 for lead in self._uow.leads.list_open(limit=1000)
                  if lead.status is LeadStatus.NEW)

    @staticmethod
    def _in_scope(lead: Lead, scope: CRMDataScope) -> bool:
        if scope.axis == "OWN":
            return lead.assigned_user_id == scope.owner_user_id
        return lead.assigned_user_id in scope.team_member_ids
