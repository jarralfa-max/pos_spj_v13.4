"""CRM-5 — Opportunities application tests (use cases + query services).

Covers happy path, permission-denied (fail closed), invalid state, stage
transition validation (required fields/min activity/backward-move/override),
idempotency, rollback, events, audit, forecast aggregation, scope
enforcement, and the CreateOpportunityFromLeadUseCase hook CRM-4 deferred.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.application.crm.authorization import (
    CRMAuthorizationPolicy,
    DenyAllCRMPermissionCheckerForTests,
)
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.opportunity_directory_query_service import (
    OpportunityDirectoryQueryService,
)
from backend.application.crm.queries.sales_pipeline_forecast_query_service import (
    SalesPipelineForecastQueryService,
)
from backend.application.crm.use_cases.create_opportunity_from_lead_use_case import (
    CreateOpportunityFromLeadUseCase,
)
from backend.application.crm.use_cases.lead_use_cases import AssignLeadUseCase, CreateLeadUseCase, \
    QualifyLeadUseCase
from backend.application.crm.use_cases.opportunity_use_cases import (
    AddOpportunityProductInterestUseCase,
    AssignOpportunityUseCase,
    CancelOpportunityUseCase,
    CreateOpportunityUseCase,
    LoseOpportunityUseCase,
    MoveOpportunityStageUseCase,
    PutOpportunityOnHoldUseCase,
    ReopenOpportunityUseCase,
    ResumeOpportunityUseCase,
    UpdateOpportunityUseCase,
    WinOpportunityUseCase,
)
from backend.domain.crm.exceptions import CRMScopeError, OpportunityNotFoundError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.shared.ids import new_uuid


def _allow():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _deny():
    return CRMAuthorizationPolicy(DenyAllCRMPermissionCheckerForTests())


def _create(conn, *, actor="u1", customer_id="cust-1", name="Venta anual", operation_id=None,
            **kwargs):
    return CreateOpportunityUseCase(_allow()).execute(
        conn, actor_user_id=actor, customer_id=customer_id, name=name,
        operation_id=operation_id or new_uuid(), **kwargs)


def _stage_id_by_code(conn, code):
    with CRMUnitOfWork(conn) as uow:
        return uow.stage_definitions.get_by_code(code).id


class TestCreate:
    def test_happy_path_uses_default_initial_stage(self, crm_conn):
        result = _create(crm_conn)
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(result.entity_id)
        assert opp.stage_id == _stage_id_by_code(crm_conn, "PROSPECTING")
        assert str(opp.code) == "OPP-000001"

    def test_explicit_stage_id_honored(self, crm_conn):
        stage_id = _stage_id_by_code(crm_conn, "PROPOSAL")
        result = _create(crm_conn, stage_id=stage_id)
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(result.entity_id)
        assert opp.stage_id == stage_id

    def test_creates_initial_stage_history_entry(self, crm_conn):
        result = _create(crm_conn)
        with CRMUnitOfWork(crm_conn) as uow:
            history = uow.stage_history.list_for_opportunity(result.entity_id)
        assert len(history) == 1
        assert history[0].from_stage_id is None

    def test_permission_denied_when_not_granted(self, crm_conn):
        result = CreateOpportunityUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", customer_id="cust-1", name="X",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, crm_conn):
        op_id = new_uuid()
        first = _create(crm_conn, operation_id=op_id)
        second = _create(crm_conn, operation_id=op_id)
        assert first.entity_id == second.entity_id
        with CRMUnitOfWork(crm_conn) as uow:
            count = uow.connection.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        assert count == 1

    def test_records_audit_and_event(self, crm_conn):
        result = _create(crm_conn)
        with CRMUnitOfWork(crm_conn) as uow:
            audit = uow.audit.list_for_opportunity(result.entity_id)
            outbox = uow.outbox.list_pending()
        assert any(a["action"] == "CRM_OPPORTUNITY_CREATED" for a in audit)
        assert any(o["event_name"] == "CRM_OPPORTUNITY_CREATED" for o in outbox)

    def test_amount_persisted_as_decimal(self, crm_conn):
        result = _create(crm_conn, amount="12345.67")
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(result.entity_id)
        from decimal import Decimal
        assert opp.amount == Decimal("12345.67")


class TestUpdate:
    def test_updates_name_and_amount(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = UpdateOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            name="Venta renovada", amount="999.99")
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(opp_id)
        from decimal import Decimal
        assert opp.name == "Venta renovada"
        assert opp.amount == Decimal("999.99")

    def test_missing_opportunity_returns_not_found(self, crm_conn):
        result = UpdateOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id="does-not-exist",
            operation_id=new_uuid(), name="X")
        assert not result.success and result.error_code == "NOT_FOUND"

    def test_rejects_float_amount(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = UpdateOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            amount=99.5)
        assert not result.success and result.error_code == "VALIDATION"


class TestAssign:
    def test_first_assignment_uses_assign_permission(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        checker_grants = {CRMPermissions.OPPORTUNITIES_ASSIGN}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignOpportunityUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, assignee_user_id="u-vendedor",
            operation_id=new_uuid())
        assert result.success

    def test_reassignment_requires_reassign_permission_not_assign(self, crm_conn):
        opp_id = _create(crm_conn, owner_user_id="u-original").entity_id
        checker_grants = {CRMPermissions.OPPORTUNITIES_ASSIGN}  # only ASSIGN, not REASSIGN

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignOpportunityUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, assignee_user_id="u-nuevo",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_missing_opportunity_returns_not_found(self, crm_conn):
        result = AssignOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id="does-not-exist",
            assignee_user_id="u2", operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class TestLifecycleTransitions:
    def test_hold_and_resume(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = PutOpportunityOnHoldUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            reason="esperando presupuesto")
        assert result.success
        result2 = ResumeOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        assert result2.success
        with CRMUnitOfWork(crm_conn) as uow:
            assert uow.opportunities.get(opp_id).status.value == "OPEN"

    def test_win_moves_to_closed_won_stage(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = WinOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(opp_id)
        assert opp.status.value == "WON"
        assert opp.stage_id == _stage_id_by_code(crm_conn, "CLOSED_WON")
        assert opp.probability == 100

    def test_lose_requires_reason_and_moves_to_closed_lost_stage(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        denied = LoseOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        assert not denied.success and denied.error_code == "VALIDATION"
        result = LoseOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            reason="presupuesto cancelado")
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            opp = uow.opportunities.get(opp_id)
        assert opp.status.value == "LOST"
        assert opp.stage_id == _stage_id_by_code(crm_conn, "CLOSED_LOST")

    def test_cancel_and_reopen(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        CancelOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            reason="cliente se retractó")
        with CRMUnitOfWork(crm_conn) as uow:
            assert uow.opportunities.get(opp_id).status.value == "CANCELLED"
        result = ReopenOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid(),
            reason="el cliente volvió a contactar")
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            assert uow.opportunities.get(opp_id).status.value == "OPEN"

    def test_permission_denied_on_win(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = WinOpportunityUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestMoveStage:
    def test_forward_move_without_required_amount_fails(self, crm_conn):
        opp_id = _create(crm_conn).entity_id  # no amount set
        proposal_stage_id = _stage_id_by_code(crm_conn, "PROPOSAL")
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get(proposal_stage_id)
            stage.required_fields = ("amount",)
            uow.stage_definitions.update(stage)
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=proposal_stage_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_forward_move_with_amount_succeeds_and_logs_history(self, crm_conn):
        opp_id = _create(crm_conn, amount="5000").entity_id
        qualification_id = _stage_id_by_code(crm_conn, "QUALIFICATION")
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=qualification_id,
            operation_id=new_uuid())
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            history = uow.stage_history.list_for_opportunity(opp_id)
        assert len(history) == 2  # creation + this move
        assert history[-1].to_stage_id == qualification_id

    def test_backward_move_without_reason_rejected(self, crm_conn):
        opp_id = _create(crm_conn, amount="5000").entity_id
        qualification_id = _stage_id_by_code(crm_conn, "QUALIFICATION")
        prospecting_id = _stage_id_by_code(crm_conn, "PROSPECTING")
        MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=qualification_id,
            operation_id=new_uuid())
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=prospecting_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_override_bypasses_required_fields_with_override_permission(self, crm_conn):
        opp_id = _create(crm_conn).entity_id  # no amount
        proposal_stage_id = _stage_id_by_code(crm_conn, "PROPOSAL")
        with CRMUnitOfWork(crm_conn) as uow:
            stage = uow.stage_definitions.get(proposal_stage_id)
            stage.required_fields = ("amount",)
            uow.stage_definitions.update(stage)
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=proposal_stage_id,
            operation_id=new_uuid(), override=True, reason="excepción autorizada por gerencia")
        assert result.success

    def test_override_without_override_permission_denied(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        proposal_stage_id = _stage_id_by_code(crm_conn, "PROPOSAL")
        checker_grants = {CRMPermissions.OPPORTUNITIES_CHANGE_STAGE}  # no OVERRIDE

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = MoveOpportunityStageUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=proposal_stage_id,
            operation_id=new_uuid(), override=True, reason="motivo")
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_move_stage_on_closed_opportunity_rejected(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        WinOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        qualification_id = _stage_id_by_code(crm_conn, "QUALIFICATION")
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id=qualification_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_missing_target_stage_returns_not_found(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = MoveOpportunityStageUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, to_stage_id="does-not-exist",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class TestProductInterest:
    def test_add_and_list(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = AddOpportunityProductInterestUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id,
            product_name="Barra energética 24pz", operation_id=new_uuid(), quantity="5",
            estimated_unit_price="120.00")
        assert result.success
        with CRMUnitOfWork(crm_conn) as uow:
            interests = uow.product_interests.list_for_opportunity(opp_id)
        assert len(interests) == 1
        assert interests[0].product_name == "Barra energética 24pz"

    def test_rejects_zero_quantity(self, crm_conn):
        opp_id = _create(crm_conn).entity_id
        result = AddOpportunityProductInterestUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, product_name="X",
            operation_id=new_uuid(), quantity="0")
        assert not result.success and result.error_code == "VALIDATION"


class TestCreateOpportunityFromLead:
    def _qualified_converted_lead(self, conn):
        lead_id = CreateLeadUseCase(_allow()).execute(
            conn, actor_user_id="u1", display_name="Restaurante El Sol",
            operation_id=new_uuid()).entity_id
        AssignLeadUseCase(_allow()).execute(
            conn, actor_user_id="u1", lead_id=lead_id, operation_id=new_uuid(),
            assignee_user_id="u-vendedor")
        QualifyLeadUseCase(_allow()).execute(
            conn, actor_user_id="u-vendedor", lead_id=lead_id, operation_id=new_uuid(),
            model="MANUAL", manual_decision="QUALIFIED")
        from backend.application.crm.use_cases.convert_lead_use_case import ConvertLeadUseCase
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        result = ConvertLeadUseCase(_allow(), CustomerAuthorizationPolicy.permissive_for_tests()).execute(
            conn, actor_user_id="u-vendedor", lead_id=lead_id, operation_id=new_uuid())
        assert result.success
        return lead_id, result.data["customer_id"]

    def test_creates_opportunity_from_customer_id_returned_by_conversion(
        self, crm_and_customers_conn,
    ):
        lead_id, customer_id = self._qualified_converted_lead(crm_and_customers_conn)
        result = CreateOpportunityFromLeadUseCase(_allow()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            customer_id=customer_id, operation_id=new_uuid())
        assert result.success
        with CRMUnitOfWork(crm_and_customers_conn) as uow:
            opp = uow.opportunities.get(result.entity_id)
        assert opp.customer_id == customer_id
        assert opp.source_lead_id == lead_id
        assert opp.owner_user_id == "u-vendedor"

    def test_rejects_lead_not_yet_converted(self, crm_and_customers_conn):
        lead_id = CreateLeadUseCase(_allow()).execute(
            crm_and_customers_conn, actor_user_id="u1", display_name="Aun no convertido",
            operation_id=new_uuid()).entity_id
        result = CreateOpportunityFromLeadUseCase(_allow()).execute(
            crm_and_customers_conn, actor_user_id="u1", lead_id=lead_id, customer_id="cust-x",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_carries_estimated_value_and_expected_date_from_lead(self, crm_and_customers_conn):
        lead_id, customer_id = self._qualified_converted_lead(crm_and_customers_conn)
        crm_and_customers_conn.execute(
            "UPDATE leads SET estimated_value=?, expected_purchase_date=? WHERE id=?",
            ("8000.00", "2026-12-01", lead_id))
        crm_and_customers_conn.commit()
        result = CreateOpportunityFromLeadUseCase(_allow()).execute(
            crm_and_customers_conn, actor_user_id="u-vendedor", lead_id=lead_id,
            customer_id=customer_id, operation_id=new_uuid())
        with CRMUnitOfWork(crm_and_customers_conn) as uow:
            opp = uow.opportunities.get(result.entity_id)
        from decimal import Decimal
        assert opp.amount == Decimal("8000.00")
        assert opp.expected_close_date == date(2026, 12, 1)


class TestSalesPipelineForecastQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return SalesPipelineForecastQueryService(conn, CRMDataScopeResolver(_Checker()))

    def test_total_and_weighted_pipeline(self, crm_conn):
        qualification_id = _stage_id_by_code(crm_conn, "QUALIFICATION")
        _create(crm_conn, amount="1000", owner_user_id="u1", stage_id=qualification_id)
        _create(crm_conn, amount="2000", owner_user_id="u1", stage_id=qualification_id)
        with CRMUnitOfWork(crm_conn) as uow:
            for opp in uow.opportunities.list_owned_by(("u1",)):
                opp.probability = 25
                uow.opportunities.update(opp)
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        forecast = service.get_forecast(CRMScopeContext(user_id="u1"))
        from decimal import Decimal
        assert forecast.total_pipeline == Decimal("3000")
        assert forecast.weighted_pipeline == Decimal("750")
        assert forecast.by_stage[qualification_id] == Decimal("3000")

    def test_won_and_lost_excluded_from_pipeline(self, crm_conn):
        opp_id = _create(crm_conn, amount="1000", owner_user_id="u1").entity_id
        WinOpportunityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, operation_id=new_uuid())
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        forecast = service.get_forecast(CRMScopeContext(user_id="u1"))
        from decimal import Decimal
        assert forecast.total_pipeline == Decimal("0")

    def test_overdue_detection(self, crm_conn):
        past_date = date.today() - timedelta(days=5)
        _create(crm_conn, amount="500", owner_user_id="u1", expected_close_date=past_date)
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        forecast = service.get_forecast(CRMScopeContext(user_id="u1"))
        assert len(forecast.overdue) == 1
        assert len(forecast.expected_closures) == 1

    def test_future_close_date_not_overdue(self, crm_conn):
        future_date = date.today() + timedelta(days=30)
        _create(crm_conn, amount="500", owner_user_id="u1", expected_close_date=future_date)
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        forecast = service.get_forecast(CRMScopeContext(user_id="u1"))
        assert len(forecast.overdue) == 0
        assert len(forecast.expected_closures) == 1

    def test_scope_denied_without_any_view_permission(self, crm_conn):
        service = self._service(crm_conn, set())
        with pytest.raises(CRMScopeError):
            service.get_forecast(CRMScopeContext(user_id="u1"))


class TestOpportunityDirectoryQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return OpportunityDirectoryQueryService(conn, CRMDataScopeResolver(_Checker()))

    def test_own_scope_sees_own_opportunity_only(self, crm_conn):
        opp_id = _create(crm_conn, owner_user_id="u-vendedor").entity_id
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        profile = service.get_profile(opp_id, CRMScopeContext(user_id="u-vendedor"))
        assert profile.opportunity.id == opp_id

    def test_own_scope_denies_other_owners_opportunity(self, crm_conn):
        opp_id = _create(crm_conn, owner_user_id="u-vendedor-a").entity_id
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        with pytest.raises(CRMScopeError):
            service.get_profile(opp_id, CRMScopeContext(user_id="u-vendedor-b"))

    def test_missing_opportunity_raises_not_found(self, crm_conn):
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_TEAM})
        with pytest.raises(OpportunityNotFoundError):
            service.get_profile("does-not-exist", CRMScopeContext(user_id="u1"))

    def test_profile_includes_stage_history_and_product_interests(self, crm_conn):
        opp_id = _create(crm_conn, owner_user_id="u1").entity_id
        AddOpportunityProductInterestUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", opportunity_id=opp_id, product_name="X",
            operation_id=new_uuid())
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        profile = service.get_profile(opp_id, CRMScopeContext(user_id="u1"))
        assert len(profile.stage_history) == 1
        assert len(profile.product_interests) == 1

    def test_list_by_stage_for_kanban_groups_correctly(self, crm_conn):
        prospecting_id = _stage_id_by_code(crm_conn, "PROSPECTING")
        qualification_id = _stage_id_by_code(crm_conn, "QUALIFICATION")
        _create(crm_conn, owner_user_id="u1", name="A")
        _create(crm_conn, owner_user_id="u1", name="B", stage_id=qualification_id)
        service = self._service(crm_conn, {CRMPermissions.OPPORTUNITIES_VIEW_OWN})
        by_stage = service.list_by_stage_for_kanban(CRMScopeContext(user_id="u1"))
        assert len(by_stage[prospecting_id]) == 1
        assert len(by_stage[qualification_id]) == 1
