"""CRMInsightsQueryService (§81-82, CRM-43) — indicadores secundarios y series
de las gráficas del tablero, calculados aquí (la UI no calcula, §90).

Respeta el alcance del usuario: prospectos, oportunidades y casos salen de
los mismos servicios de directorio (OWN/TEAM/BRANCH/COMPANY); clientes y
segmentos son globales (decisión del usuario, 2026-10-08).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.lead_directory_query_service import (
    LeadDirectoryQueryService,
)
from backend.application.crm.queries.opportunity_directory_query_service import (
    OpportunityDirectoryQueryService,
)
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


@dataclass(frozen=True)
class CRMInsights:
    active_customers: int = 0
    lead_conversion_pct: Decimal = Decimal("0")
    opportunities_won: int = 0
    won_value: Decimal = Decimal("0")
    open_cases: int = 0
    customers_without_follow_up: int = 0
    leads_by_source: tuple[tuple[str, int], ...] = ()
    opportunities_by_outcome: tuple[tuple[str, int], ...] = ()
    pipeline_by_owner: tuple[tuple[str | None, Decimal], ...] = ()
    cases_by_type: tuple[tuple[str, int], ...] = ()
    sla_compliance: tuple[tuple[str, int], ...] = ()
    customers_by_segment: tuple[tuple[str, int], ...] = ()
    unavailable: tuple[str, ...] = field(default_factory=tuple)


class CRMInsightsQueryService:
    def __init__(self, connection, scope_resolver: CRMDataScopeResolver,
                 authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._uow = CRMUnitOfWork(connection)
        self._scope = scope_resolver
        self._auth = authorization or CRMAuthorizationPolicy()

    def get(self, context: CRMScopeContext) -> CRMInsights:
        unavailable: list[str] = []
        values: dict = {}

        try:
            leads = LeadDirectoryQueryService(self._conn, self._scope, self._auth).list_directory(
                context, limit=5000)
            total = len(leads)
            converted = sum(1 for lead in leads if lead.status.value == "CONVERTED")
            values["lead_conversion_pct"] = (
                (Decimal(converted) * 100 / Decimal(total)).quantize(Decimal("0.1"))
                if total else Decimal("0"))
            values["leads_by_source"] = tuple(Counter(lead.source.value for lead in leads)
                                              .most_common())
        except Exception:  # noqa: BLE001 — sin alcance de prospectos
            unavailable.append("leads")

        try:
            opps = OpportunityDirectoryQueryService(self._conn, self._scope).list_directory(
                context, limit=5000)
            won = [o for o in opps if o.status.value == "WON"]
            values["opportunities_won"] = len(won)
            values["won_value"] = sum((o.amount or Decimal("0") for o in won), Decimal("0"))
            values["opportunities_by_outcome"] = tuple(
                Counter(o.status.value for o in opps).most_common())
            by_owner: dict = {}
            for o in opps:
                if o.status.value in ("OPEN", "ON_HOLD"):
                    by_owner[o.owner_user_id] = by_owner.get(o.owner_user_id, Decimal("0")) + (
                        o.amount or Decimal("0"))
            values["pipeline_by_owner"] = tuple(sorted(by_owner.items(),
                                                       key=lambda kv: kv[1], reverse=True))
        except Exception:  # noqa: BLE001
            unavailable.append("opportunities")

        try:
            from backend.application.customer_service.queries.service_case_query_service import (
                ServiceCaseQueryService,
            )
            rows = ServiceCaseQueryService(self._conn, self._scope, self._auth).list_rows(
                context, limit=5000)
            open_rows = [r for r in rows if r.case.status.value not in (
                "RESOLVED", "CLOSED", "CANCELLED")]
            values["open_cases"] = len(open_rows)
            values["cases_by_type"] = tuple(Counter(r.case.case_type.value for r in rows)
                                            .most_common())
            values["sla_compliance"] = tuple(Counter(
                r.sla.effective_breach_status().value for r in rows if r.sla is not None)
                .most_common())
        except Exception:  # noqa: BLE001
            unavailable.append("cases")

        values["active_customers"] = self._uow.insights.active_customers()
        values["customers_without_follow_up"] = self._uow.insights.without_follow_up()
        if self._auth.has_permission(context.user_id, CRMPermissions.SEGMENTS_VIEW):
            values["customers_by_segment"] = tuple(self._uow.insights.customers_by_segment())
        return CRMInsights(unavailable=tuple(unavailable), **values)
