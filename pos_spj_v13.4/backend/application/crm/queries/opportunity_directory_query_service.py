"""OpportunityDirectoryQueryService (§57) — read side for Opportunities.
Reads only; never mutates. Second consumer of CRM-2's
``CRMDataScopeResolver`` (after LeadDirectoryQueryService) — same OWN/TEAM
axes, see backend/application/crm/data_scope.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.crm.data_scope import CRMDataScope, CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import OPPORTUNITY_VIEW_SCOPE_PERMISSIONS
from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.opportunity_product_interest import OpportunityProductInterest
from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.domain.crm.exceptions import CRMScopeError, OpportunityNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class OpportunityProfile:
    opportunity: Opportunity
    stage_history: list[OpportunityStageHistory] = field(default_factory=list)
    product_interests: list[OpportunityProductInterest] = field(default_factory=list)


class OpportunityDirectoryQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._scope_resolver = scope_resolver

    def get_profile(self, opportunity_id: str, context: CRMScopeContext) -> OpportunityProfile:
        scope = self._scope_resolver.resolve_view_scope(context, OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        opportunity = self._uow.opportunities.get(opportunity_id)
        if opportunity is None:
            raise OpportunityNotFoundError(f"Oportunidad {opportunity_id!r} no existe")
        if not self._in_scope(opportunity, scope):
            raise CRMScopeError(
                f"La oportunidad {opportunity_id!r} está fuera del alcance "
                f"({scope.axis}) del usuario")
        return OpportunityProfile(
            opportunity=opportunity,
            stage_history=self._uow.stage_history.list_for_opportunity(opportunity_id),
            product_interests=self._uow.product_interests.list_for_opportunity(opportunity_id))

    def list_directory(self, context: CRMScopeContext, *, limit: int = 200,
                        offset: int = 0) -> list[Opportunity]:
        scope = self._scope_resolver.resolve_view_scope(context, OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
        return self._uow.opportunities.list_owned_by(owner_ids, limit=limit, offset=offset)

    def list_for_customer(self, customer_id: str, context: CRMScopeContext, *,
                          limit: int = 200) -> list[Opportunity]:
        """CRM-12: Customer 360's "pipeline" tab. Fetches by customer_id (not
        owner) then filters through the caller's resolved scope, same
        in-scope-after-fetch check ``get_profile`` already does — a customer
        can have opportunities owned by different reps, and the caller only
        sees the ones their OWN/TEAM grant actually covers."""
        scope = self._scope_resolver.resolve_view_scope(context, OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        opportunities = self._uow.opportunities.list_for_customer(customer_id, limit=limit)
        return [o for o in opportunities if self._in_scope(o, scope)]

    def list_by_stage_for_kanban(
        self, context: CRMScopeContext, *, limit_per_stage: int = 200,
    ) -> dict[str, list[Opportunity]]:
        """Groups the caller's in-scope opportunities by ``stage_id`` — the
        read side of ``crm.pipeline``'s Kanban view (§19-22)."""
        scope = self._scope_resolver.resolve_view_scope(context, OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
        opportunities = self._uow.opportunities.list_owned_by(owner_ids, limit=2000)
        by_stage: dict[str, list[Opportunity]] = {}
        for opportunity in opportunities:
            bucket = by_stage.setdefault(opportunity.stage_id, [])
            if len(bucket) < limit_per_stage:
                bucket.append(opportunity)
        return by_stage

    @staticmethod
    def _in_scope(opportunity: Opportunity, scope: CRMDataScope) -> bool:
        if scope.axis == "OWN":
            return opportunity.owner_user_id == scope.owner_user_id
        return opportunity.owner_user_id in scope.team_member_ids
