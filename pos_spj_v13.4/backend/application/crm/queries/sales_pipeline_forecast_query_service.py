"""SalesPipelineForecastQueryService (§19-22): "pipeline total/ponderado,
por etapa, cierres esperados, vencidas, sin seguimiento. CRM calcula
forecast operativo; BI hace modelos analíticos avanzados; no mezclar con
forecast de abastecimiento." Reads only; never mutates.

``stagnant`` (§19-22's "sin seguimiento") is approximated here as "no field
has changed in N days" (``updated_at`` age) because Activities (CRM-6)
doesn't exist yet to supply a real last-touched-by-an-activity signal — the
same kind of explicit, documented stopgap CRM-4 used for
``activities_logged_count=0`` in ``MoveOpportunityStageUseCase``. Revisit
once CRM-6 lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import OPPORTUNITY_VIEW_SCOPE_PERMISSIONS
from backend.domain.crm.entities.opportunity import Opportunity
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class SalesPipelineForecast:
    total_pipeline: Decimal
    weighted_pipeline: Decimal
    by_stage: dict[str, Decimal] = field(default_factory=dict)
    expected_closures: list[Opportunity] = field(default_factory=list)
    overdue: list[Opportunity] = field(default_factory=list)
    stagnant: list[Opportunity] = field(default_factory=list)
    # CRM-15 (§90 dashboard KPI "Oportunidades abiertas"): additive — the
    # count was already computed as len(open_opportunities) below and
    # simply never surfaced; no new query needed.
    open_count: int = 0


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


class SalesPipelineForecastQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._scope_resolver = scope_resolver

    def get_forecast(
        self, context: CRMScopeContext, *, as_of: date | None = None,
        stagnant_after_days: int = 14,
    ) -> SalesPipelineForecast:
        scope = self._scope_resolver.resolve_view_scope(context, OPPORTUNITY_VIEW_SCOPE_PERMISSIONS)
        owner_ids = (scope.owner_user_id,) if scope.axis == "OWN" else scope.team_member_ids
        today = as_of or _today_utc()

        open_opportunities = self._uow.opportunities.list_open_owned_by(owner_ids)

        total = Decimal("0")
        weighted = Decimal("0")
        by_stage: dict[str, Decimal] = {}
        expected_closures: list[Opportunity] = []
        overdue: list[Opportunity] = []
        stagnant: list[Opportunity] = []

        for opportunity in open_opportunities:
            amount = opportunity.amount or Decimal("0")
            total += amount
            weighted += amount * Decimal(opportunity.probability) / Decimal(100)
            by_stage[opportunity.stage_id] = by_stage.get(opportunity.stage_id, Decimal("0")) + amount

            if opportunity.expected_close_date is not None:
                expected_closures.append(opportunity)
                if opportunity.expected_close_date < today:
                    overdue.append(opportunity)

            updated_date = date.fromisoformat(opportunity.updated_at[:10])
            if (today - updated_date).days >= stagnant_after_days:
                stagnant.append(opportunity)

        expected_closures.sort(key=lambda o: o.expected_close_date)
        return SalesPipelineForecast(
            total_pipeline=total, weighted_pipeline=weighted, by_stage=by_stage,
            expected_closures=expected_closures, overdue=overdue, stagnant=stagnant,
            open_count=len(open_opportunities))
