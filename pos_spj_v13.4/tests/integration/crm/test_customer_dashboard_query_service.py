"""CRM-15 — CustomerDashboardQueryService: the 6-KPI dashboard, pure
composition over CRM-4/5/6/7's already-built query services.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver
from backend.application.crm.queries.customer_dashboard_query_service import (
    CustomerDashboardQueryService,
)
from backend.application.crm.use_cases.activity_use_cases import CreateCRMActivityUseCase
from backend.application.crm.use_cases.lead_use_cases import AssignLeadUseCase, CreateLeadUseCase
from backend.application.crm.use_cases.opportunity_use_cases import CreateOpportunityUseCase
from backend.application.crm.use_cases.task_use_cases import CreateCRMTaskUseCase
from backend.application.customer_service.use_cases.service_case_use_cases import (
    CreateServiceCaseUseCase,
)
from backend.application.customer_service.use_cases.service_level_policy_use_cases import (
    CreateServiceLevelPolicyUseCase,
)
from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.shared.ids import new_uuid


class _AllowAllChecker:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


def _allow_crm():
    return CRMAuthorizationPolicy(_AllowAllChecker())


def _scope_resolver():
    return CRMDataScopeResolver(_AllowAllChecker())


def _service(conn) -> CustomerDashboardQueryService:
    return CustomerDashboardQueryService(conn, _scope_resolver(), _allow_crm())


def _new_lead(conn) -> str:
    """A freshly-created, unassigned lead — stays in status NEW."""
    result = CreateLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", display_name=f"Prospecto {new_uuid()}",
        operation_id=new_uuid(), allow_duplicate=True)
    assert result.success
    return result.entity_id


def _assigned_lead(conn, *, owner="u1") -> str:
    """A lead already claimed by someone — advances NEW -> ASSIGNED."""
    lead_id = _new_lead(conn)
    AssignLeadUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
        assignee_user_id=owner)
    return lead_id


def _seeded_stage_id(conn) -> str:
    with CRMUnitOfWork(conn) as uow:
        stages = uow.stage_definitions.list_active_ordered()
    assert stages, "migration 183 should have seeded default stages"
    return stages[0].id


def _opportunity(conn, *, owner="u1", amount="1000", probability=50) -> str:
    result = CreateOpportunityUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", customer_id="cust-1", name="Oportunidad de prueba",
        operation_id=new_uuid(), stage_id=_seeded_stage_id(conn), owner_user_id=owner,
        amount=amount, probability=probability)
    assert result.success
    return result.entity_id


def _overdue_activity(conn, *, assignee="u1") -> str:
    result = CreateCRMActivityUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", activity_type=CRMActivityType.CALL.value,
        related_entity_type=CRMRelatedEntityType.CUSTOMER.value, related_entity_id="cust-1",
        subject="Llamar", operation_id=new_uuid(), assigned_user_id=assignee,
        scheduled_at="2020-01-01T10:00:00+00:00")
    assert result.success
    return result.entity_id


def _overdue_task(conn, *, assignee="u1") -> str:
    result = CreateCRMTaskUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1",
        related_entity_type=CRMRelatedEntityType.CUSTOMER.value, related_entity_id="cust-1",
        title="Enviar cotización", due_at="2020-01-01T00:00:00+00:00",
        operation_id=new_uuid(), assigned_user_id=assignee)
    assert result.success
    return result.entity_id


def _breached_case(conn) -> str:
    CreateServiceLevelPolicyUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", code="STANDARD", name="Estándar",
        first_response_minutes=30, resolution_minutes=60, operation_id=new_uuid())
    result = CreateServiceCaseUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", customer_id="cust-1", case_type="QUESTION",
        subject="Consulta de prueba", operation_id=new_uuid())
    assert result.success
    return result.entity_id


class TestCustomerDashboardQueryService:
    def test_empty_dashboard_has_zeroed_kpis(self, crm_and_service_conn):
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.leads_new_count == 0
        assert view.leads_pending_count == 0
        assert view.opportunities_open_count == 0
        assert view.weighted_pipeline == Decimal("0")
        assert view.overdue_activities_count == 0
        assert view.cases_out_of_sla_count == 0

    def test_counts_new_leads_company_wide(self, crm_and_service_conn):
        """Leads nuevos are unassigned by definition — this KPI is
        deliberately NOT scoped to the viewer (see LeadDirectoryQueryService
        .count_new()'s docstring)."""
        _new_lead(crm_and_service_conn)
        _new_lead(crm_and_service_conn)
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.leads_new_count == 2
        assert view.leads_pending_count == 0

    def test_counts_pending_leads_assigned_to_viewer(self, crm_and_service_conn):
        _assigned_lead(crm_and_service_conn, owner="u1")
        _assigned_lead(crm_and_service_conn, owner="u1")
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.leads_pending_count == 2
        assert view.leads_new_count == 0

    def test_pending_leads_outside_scope_are_not_counted(self, crm_and_service_conn):
        _assigned_lead(crm_and_service_conn, owner="someone-else")
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.leads_pending_count == 0

    def test_open_opportunities_and_weighted_pipeline(self, crm_and_service_conn):
        _opportunity(crm_and_service_conn, amount="1000", probability=50)
        _opportunity(crm_and_service_conn, amount="2000", probability=25)
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.opportunities_open_count == 2
        assert view.total_pipeline == Decimal("3000")
        assert view.weighted_pipeline == Decimal("1000")  # 500 + 500

    def test_pipeline_by_stage_uses_stage_names(self, crm_and_service_conn):
        _opportunity(crm_and_service_conn, amount="1000")
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert len(view.pipeline_by_stage) == 1
        assert view.pipeline_by_stage[0].stage_name == "Prospección"
        assert view.pipeline_by_stage[0].amount == Decimal("1000")

    def test_overdue_activities_and_tasks_counted_and_listed(self, crm_and_service_conn):
        _overdue_activity(crm_and_service_conn)
        _overdue_task(crm_and_service_conn)
        view = _service(crm_and_service_conn).get_dashboard(actor_user_id="u1")
        assert view.overdue_activities_count == 2
        assert len(view.recent_overdue_activities) == 1
        assert len(view.recent_overdue_tasks) == 1

    def test_overdue_merges_across_team_without_duplicates(self, crm_and_service_conn):
        _overdue_activity(crm_and_service_conn, assignee="u1")
        _overdue_activity(crm_and_service_conn, assignee="u2")
        view = _service(crm_and_service_conn).get_dashboard(
            actor_user_id="u1", team_member_ids=("u1", "u2"))
        assert view.overdue_activities_count == 2

    def test_cases_out_of_sla_counted(self, crm_and_service_conn):
        _breached_case(crm_and_service_conn)
        view = _service(crm_and_service_conn).get_dashboard(
            actor_user_id="u1", as_of="2099-01-01T00:00:00+00:00")
        assert view.cases_out_of_sla_count == 1
        assert len(view.recent_breached_cases) == 1

    def test_case_within_sla_not_counted(self, crm_and_service_conn):
        _breached_case(crm_and_service_conn)
        view = _service(crm_and_service_conn).get_dashboard(
            actor_user_id="u1", as_of="2020-01-01T00:00:00+00:00")
        assert view.cases_out_of_sla_count == 0

    def test_recent_limit_caps_lists_but_not_counts(self, crm_and_service_conn):
        for _ in range(3):
            _overdue_activity(crm_and_service_conn)
        view = _service(crm_and_service_conn).get_dashboard(
            actor_user_id="u1", recent_limit=1)
        assert view.overdue_activities_count == 3
        assert len(view.recent_overdue_activities) == 1
