"""CustomerDashboardQueryService (§57, §90) — the CRM-15 dashboard: "máx. 6
KPIs principales (Leads nuevos, Leads por atender, Oportunidades abiertas,
Pipeline ponderado, Actividades vencidas, Casos fuera de SLA) + secundarios.
La UI no calcula KPIs." Pure composition, same discipline as
``Customer360QueryService`` (CRM-12)/``CRMBIExportQueryService`` (CRM-13):
every number here is read from an already-built query service, never
re-derived with parallel logic.

Scoped like every other CRM query service (OWN/TEAM via
``CRMScopeContext``), not company-wide like CRM-13's BI export — a
dashboard answers "what's on MY plate," not "give BI a full snapshot."
Overdue activities/tasks and SLA breaches are resolved per member of
``team_member_ids`` (or just the actor when none given) and merged, since
``CRMActivityQueryService``/``CRMTaskQueryService``.``list_overdue_for()``
takes one user id at a time (§23-26 never asked for a batch variant).

Graceful degradation: each section is wrapped in ``_safe()`` (same helper
Customer360 uses) so a caller missing one section's permission still sees
the rest of their dashboard, never a hard failure — no single role in
§59-61's suggested matrix holds every permission a 6-KPI dashboard touches
at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.queries.crm_activity_query_service import CRMActivityQueryService
from backend.application.crm.queries.crm_task_query_service import CRMTaskQueryService
from backend.application.crm.queries.lead_directory_query_service import LeadDirectoryQueryService
from backend.application.crm.queries.sales_pipeline_forecast_query_service import (
    SalesPipelineForecastQueryService,
)
from backend.application.customer_service.queries.sla_query_service import SLAQueryService
from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import LeadStatus
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork

_PENDING_LEAD_STATUSES = frozenset({
    LeadStatus.ASSIGNED, LeadStatus.CONTACTED, LeadStatus.NURTURING})


@dataclass(frozen=True)
class PipelineStageSlice:
    stage_name: str
    amount: Decimal


@dataclass(frozen=True)
class CustomerDashboardView:
    # -- primary KPIs (§90's exact six) --------------------------------------
    leads_new_count: int = 0
    leads_pending_count: int = 0
    opportunities_open_count: int = 0
    weighted_pipeline: Decimal = Decimal("0")
    overdue_activities_count: int = 0
    cases_out_of_sla_count: int = 0
    # -- secondary --------------------------------------------------------
    total_pipeline: Decimal = Decimal("0")
    pipeline_by_stage: tuple[PipelineStageSlice, ...] = ()
    recent_overdue_activities: tuple[CRMActivity, ...] = ()
    recent_overdue_tasks: tuple[CRMTask, ...] = ()
    recent_breached_cases: tuple[SLAInstance, ...] = ()


class CustomerDashboardQueryService:
    def __init__(
        self, connection, crm_scope_resolver: CRMDataScopeResolver,
        crm_authorization: CRMAuthorizationPolicy | None = None,
    ) -> None:
        self._connection = connection
        self._crm_scope_resolver = crm_scope_resolver
        self._crm_auth = crm_authorization or CRMAuthorizationPolicy()

    def get_dashboard(
        self, *, actor_user_id: str, team_member_ids: tuple[str, ...] = (),
        recent_limit: int = 5, as_of: str | None = None,
    ) -> CustomerDashboardView:
        context = CRMScopeContext(user_id=actor_user_id, team_member_ids=team_member_ids)
        members = team_member_ids or (actor_user_id,)

        lead_service = LeadDirectoryQueryService(
            self._connection, self._crm_scope_resolver, self._crm_auth)
        leads = self._safe(
            lambda: lead_service.list_directory(context, limit=500), default=[])
        leads_pending = sum(1 for lead in leads if lead.status in _PENDING_LEAD_STATUSES)
        leads_new = self._safe(
            lambda: lead_service.count_new(actor_user_id=actor_user_id), default=0)

        forecast_as_of = date.fromisoformat(as_of[:10]) if as_of else None
        forecast = self._safe(
            lambda: SalesPipelineForecastQueryService(self._connection, self._crm_scope_resolver)
            .get_forecast(context, as_of=forecast_as_of))
        pipeline_by_stage = self._stage_slices(forecast.by_stage) if forecast else ()

        overdue_activities = self._safe(lambda: self._collect_overdue_activities(
            members, actor_user_id=actor_user_id, as_of=as_of), default=[])
        overdue_tasks = self._safe(lambda: self._collect_overdue_tasks(
            members, actor_user_id=actor_user_id, as_of=as_of), default=[])

        breached_cases = self._safe(
            lambda: SLAQueryService(self._connection, self._crm_auth)
            .list_breached(actor_user_id=actor_user_id, as_of=as_of), default=[])

        return CustomerDashboardView(
            leads_new_count=leads_new,
            leads_pending_count=leads_pending,
            opportunities_open_count=forecast.open_count if forecast else 0,
            weighted_pipeline=forecast.weighted_pipeline if forecast else Decimal("0"),
            overdue_activities_count=len(overdue_activities) + len(overdue_tasks),
            cases_out_of_sla_count=len(breached_cases),
            total_pipeline=forecast.total_pipeline if forecast else Decimal("0"),
            pipeline_by_stage=pipeline_by_stage,
            recent_overdue_activities=tuple(overdue_activities[:recent_limit]),
            recent_overdue_tasks=tuple(overdue_tasks[:recent_limit]),
            recent_breached_cases=tuple(breached_cases[:recent_limit]),
        )

    def _collect_overdue_activities(
        self, members: tuple[str, ...], *, actor_user_id: str, as_of: str | None,
    ) -> list[CRMActivity]:
        service = CRMActivityQueryService(self._connection, self._crm_auth)
        merged: dict[str, CRMActivity] = {}
        for member_id in members:
            for activity in service.list_overdue_for(
                    member_id, actor_user_id=actor_user_id, as_of=as_of):
                merged[activity.id] = activity
        return sorted(merged.values(), key=lambda a: a.scheduled_at or "")

    def _collect_overdue_tasks(
        self, members: tuple[str, ...], *, actor_user_id: str, as_of: str | None,
    ) -> list[CRMTask]:
        service = CRMTaskQueryService(self._connection, self._crm_auth)
        merged: dict[str, CRMTask] = {}
        for member_id in members:
            for task in service.list_overdue_for(
                    member_id, actor_user_id=actor_user_id, as_of=as_of):
                merged[task.id] = task
        return sorted(merged.values(), key=lambda t: t.due_at or "")

    def _stage_slices(self, by_stage: dict[str, Decimal]) -> tuple[PipelineStageSlice, ...]:
        if not by_stage:
            return ()
        uow = CRMUnitOfWork(self._connection)
        stages = uow.stage_definitions.list_active_ordered()
        names_by_id = {stage.id: stage.name for stage in stages}
        ordered_ids = [stage.id for stage in stages if stage.id in by_stage]
        ordered_ids += [stage_id for stage_id in by_stage if stage_id not in names_by_id]
        return tuple(
            PipelineStageSlice(stage_name=names_by_id.get(stage_id, stage_id),
                               amount=by_stage[stage_id])
            for stage_id in ordered_ids)

    @staticmethod
    def _safe(getter, *, default=None):
        try:
            return getter()
        except CRMDomainError:
            return default
