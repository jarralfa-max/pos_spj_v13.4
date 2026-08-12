"""CRM-7 — Service Case application tests (use cases + query services).

Covers happy path, permission-denied (fail closed), invalid state,
idempotency, rollback, audit, SLA lifecycle (creation from resolved
policy/pause-resume/first-response/resolution), escalation, sensitive-case
masking, and OWN/TEAM scope enforcement (reusing CRM-2's
CRMDataScopeResolver).
"""

from __future__ import annotations

import pytest

from backend.application.crm.authorization import (
    CRMAuthorizationPolicy,
    DenyAllCRMPermissionCheckerForTests,
)
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.permissions import CRMPermissions
from backend.application.customer_service.queries.service_case_query_service import (
    ServiceCaseQueryService,
)
from backend.application.customer_service.queries.sla_query_service import SLAQueryService
from backend.application.customer_service.use_cases.escalate_service_case_use_case import (
    EscalateServiceCaseUseCase,
)
from backend.application.customer_service.use_cases.service_case_use_cases import (
    AssignServiceCaseUseCase,
    CancelServiceCaseUseCase,
    CloseServiceCaseUseCase,
    CreateServiceCaseUseCase,
    RecordFirstResponseUseCase,
    ResolveServiceCaseUseCase,
    ResumeServiceCaseUseCase,
    StartServiceCaseProgressUseCase,
    UpdateServiceCaseUseCase,
    WaitForCustomerUseCase,
)
from backend.application.customer_service.use_cases.service_level_policy_use_cases import (
    CreateServiceLevelPolicyUseCase,
    OverrideSLAUseCase,
)
from backend.domain.crm.exceptions import CRMPermissionDeniedError, CRMScopeError
from backend.domain.customer_service.enums import SLABreachStatus
from backend.domain.customer_service.exceptions import ServiceCaseNotFoundError
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)
from backend.shared.ids import new_uuid


def _allow():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _deny():
    return CRMAuthorizationPolicy(DenyAllCRMPermissionCheckerForTests())


def _create(conn, *, actor="u1", customer_id="cust-1", case_type="COMPLAINT",
            subject="Producto en mal estado", operation_id=None, **kwargs):
    return CreateServiceCaseUseCase(_allow()).execute(
        conn, actor_user_id=actor, customer_id=customer_id, case_type=case_type,
        subject=subject, operation_id=operation_id or new_uuid(), **kwargs)


def _create_policy(conn, *, code=None, first_response_minutes=60,
                    resolution_minutes=480, **kwargs):
    # UUIDv7 is time-ordered — its leading hex chars barely change between
    # calls microseconds apart, so truncating would collide. Use the full id.
    code = code or f"POLICY-{new_uuid()}"
    return CreateServiceLevelPolicyUseCase(_allow()).execute(
        conn, actor_user_id="u1", code=code, name=code.title(),
        first_response_minutes=first_response_minutes, resolution_minutes=resolution_minutes,
        operation_id=new_uuid(), **kwargs)


class TestCreate:
    def test_happy_path(self, cs_conn):
        result = _create(cs_conn)
        assert result.success

    def test_permission_denied(self, cs_conn):
        result = CreateServiceCaseUseCase(_deny()).execute(
            cs_conn, actor_user_id="u1", customer_id="cust-1", case_type="COMPLAINT",
            subject="X", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, cs_conn):
        op_id = new_uuid()
        first = _create(cs_conn, operation_id=op_id)
        second = _create(cs_conn, operation_id=op_id)
        assert first.entity_id == second.entity_id
        count = cs_conn.execute("SELECT COUNT(*) FROM service_cases").fetchone()[0]
        assert count == 1

    def test_missing_subject_is_validation_error(self, cs_conn):
        result = CreateServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", customer_id="cust-1", case_type="COMPLAINT",
            subject="   ", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_creates_sla_instance_when_policy_matches(self, cs_conn):
        _create_policy(cs_conn)
        result = _create(cs_conn)
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(result.entity_id)
        assert sla is not None

    def test_no_sla_instance_when_no_policy_configured(self, cs_conn):
        result = _create(cs_conn)
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(result.entity_id)
        assert sla is None

    def test_records_audit_and_event(self, cs_conn):
        result = _create(cs_conn)
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            audit = uow.audit.list_for_case(result.entity_id)
            outbox = uow.outbox.list_pending()
        assert any(a["action"] == "CASE_CREATED" for a in audit)
        assert any(o["event_name"] == "CASE_CREATED" for o in outbox)


class TestUpdate:
    def test_updates_subject_and_priority(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        result = UpdateServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid(),
            subject="Actualizado", priority="CRITICAL")
        assert result.success
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = uow.cases.get(case_id)
        assert case.subject == "Actualizado"
        assert case.priority.value == "CRITICAL"

    def test_missing_case_returns_not_found(self, cs_conn):
        result = UpdateServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id="does-not-exist", operation_id=new_uuid(),
            subject="X")
        assert not result.success and result.error_code == "NOT_FOUND"


class TestAssign:
    def test_first_assignment_uses_assign_permission(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        checker_grants = {CRMPermissions.CASES_ASSIGN}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignServiceCaseUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u2",
            operation_id=new_uuid())
        assert result.success

    def test_reassignment_requires_reassign_not_assign_permission(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-original",
            operation_id=new_uuid())
        checker_grants = {CRMPermissions.CASES_ASSIGN}  # only ASSIGN, not REASSIGN

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignServiceCaseUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-nuevo",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestLifecycleAndSLA:
    def _qualified_case(self, conn):
        _create_policy(conn, first_response_minutes=30, resolution_minutes=240)
        case_id = _create(conn).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u1",
            operation_id=new_uuid())
        StartServiceCaseProgressUseCase(_allow()).execute(
            conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        return case_id

    def test_wait_for_customer_pauses_sla(self, cs_conn):
        case_id = self._qualified_case(cs_conn)
        WaitForCustomerUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
        assert sla.effective_breach_status() == SLABreachStatus.PAUSED

    def test_resume_unpauses_sla(self, cs_conn):
        case_id = self._qualified_case(cs_conn)
        WaitForCustomerUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        ResumeServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
        assert sla.paused is False

    def test_record_first_response(self, cs_conn):
        case_id = self._qualified_case(cs_conn)
        result = RecordFirstResponseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        assert result.success
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
        assert sla.first_response_at is not None

    def test_resolve_completes_sla_and_creates_resolution(self, cs_conn):
        case_id = self._qualified_case(cs_conn)
        result = ResolveServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id,
            resolution_summary="Se repuso el producto", operation_id=new_uuid())
        assert result.success
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = uow.cases.get(case_id)
            sla = uow.sla_instances.get_for_case(case_id)
            resolution = uow.resolutions.get_for_case(case_id)
        assert case.status.value == "RESOLVED"
        assert sla.effective_breach_status() == SLABreachStatus.COMPLETED
        assert resolution.resolution_summary == "Se repuso el producto"

    def test_close_and_cancel(self, cs_conn):
        case_id = self._qualified_case(cs_conn)
        ResolveServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, resolution_summary="Resuelto",
            operation_id=new_uuid())
        result = CloseServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, operation_id=new_uuid())
        assert result.success

        case_id2 = self._qualified_case(cs_conn)
        cancel_denied = CancelServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id2, operation_id=new_uuid())
        assert not cancel_denied.success  # no reason
        cancel_ok = CancelServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id2, operation_id=new_uuid(),
            reason="cliente se retractó")
        assert cancel_ok.success


class TestEscalate:
    def test_escalate_bumps_sla_level_and_logs_history(self, cs_conn):
        _create_policy(cs_conn)
        case_id = _create(cs_conn).entity_id
        result = EscalateServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, reason="CRITICAL_CASE",
            escalated_to_user_id="u-super", operation_id=new_uuid())
        assert result.success and result.data["level"] == 1
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            case = uow.cases.get(case_id)
            sla = uow.sla_instances.get_for_case(case_id)
            history = uow.escalations.list_for_case(case_id)
        assert case.status.value == "ESCALATED"
        assert sla.escalation_level == 1
        assert len(history) == 1

    def test_escalate_without_sla_still_transitions_case(self, cs_conn):
        case_id = _create(cs_conn).entity_id  # no policy configured
        result = EscalateServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, reason="OTHER",
            escalated_to_user_id="u-super", operation_id=new_uuid())
        assert result.success

    def test_permission_denied(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        result = EscalateServiceCaseUseCase(_deny()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, reason="OTHER",
            escalated_to_user_id="u-super", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestOverrideSLA:
    def test_override_marks_sla_completed(self, cs_conn):
        _create_policy(cs_conn)
        case_id = _create(cs_conn).entity_id
        result = OverrideSLAUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id,
            reason="excepción autorizada por gerencia", operation_id=new_uuid())
        assert result.success
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
        assert sla.effective_breach_status() == SLABreachStatus.COMPLETED

    def test_requires_reason(self, cs_conn):
        _create_policy(cs_conn)
        case_id = _create(cs_conn).entity_id
        result = OverrideSLAUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, reason="", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestServiceCaseQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return ServiceCaseQueryService(conn, CRMDataScopeResolver(_Checker()),
                                       CRMAuthorizationPolicy(_Checker()))

    def test_own_scope_sees_own_case_only(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-agente",
            operation_id=new_uuid())
        service = self._service(cs_conn, {CRMPermissions.CASES_VIEW_OWN})
        profile = service.get_profile(case_id, CRMScopeContext(user_id="u-agente"))
        assert profile.id == case_id

    def test_own_scope_denies_other_owners_case(self, cs_conn):
        case_id = _create(cs_conn).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-agente-a",
            operation_id=new_uuid())
        service = self._service(cs_conn, {CRMPermissions.CASES_VIEW_OWN})
        with pytest.raises(CRMScopeError):
            service.get_profile(case_id, CRMScopeContext(user_id="u-agente-b"))

    def test_get_profile_missing_case_raises_not_found(self, cs_conn):
        service = self._service(cs_conn, {CRMPermissions.CASES_VIEW_TEAM})
        with pytest.raises(ServiceCaseNotFoundError):
            service.get_profile("does-not-exist", CRMScopeContext(user_id="u1"))

    def test_sensitive_case_denied_without_view_sensitive_permission(self, cs_conn):
        case_id = _create(cs_conn, is_sensitive=True).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-agente",
            operation_id=new_uuid())
        service = self._service(cs_conn, {CRMPermissions.CASES_VIEW_OWN})  # no VIEW_SENSITIVE
        with pytest.raises(CRMPermissionDeniedError):
            service.get_profile(case_id, CRMScopeContext(user_id="u-agente"))

    def test_sensitive_case_allowed_with_view_sensitive_permission(self, cs_conn):
        case_id = _create(cs_conn, is_sensitive=True).entity_id
        AssignServiceCaseUseCase(_allow()).execute(
            cs_conn, actor_user_id="u1", case_id=case_id, assignee_user_id="u-agente",
            operation_id=new_uuid())
        service = self._service(
            cs_conn, {CRMPermissions.CASES_VIEW_OWN, CRMPermissions.CASES_VIEW_SENSITIVE})
        profile = service.get_profile(case_id, CRMScopeContext(user_id="u-agente"))
        assert profile.id == case_id

    def test_list_directory_masks_sensitive_cases(self, cs_conn):
        normal_id = _create(cs_conn, subject="Normal").entity_id
        sensitive_id = _create(cs_conn, subject="Sensible", is_sensitive=True).entity_id
        for cid in (normal_id, sensitive_id):
            AssignServiceCaseUseCase(_allow()).execute(
                cs_conn, actor_user_id="u1", case_id=cid, assignee_user_id="u-agente",
                operation_id=new_uuid())
        service = self._service(cs_conn, {CRMPermissions.CASES_VIEW_OWN})
        results = service.list_directory(CRMScopeContext(user_id="u-agente"))
        assert [c.id for c in results] == [normal_id]


class TestSLAQueryService:
    def test_list_breached_and_at_risk(self, cs_conn):
        from datetime import datetime, timedelta, timezone

        _create_policy(cs_conn, code="TIGHT", first_response_minutes=10,
                        resolution_minutes=60)
        case_id = _create(cs_conn).entity_id
        service = SLAQueryService(cs_conn, _allow())
        far_future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(
            timespec="seconds")
        far_past = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(
            timespec="seconds")
        assert len(service.list_breached(actor_user_id="u1", as_of=far_past)) == 0
        breached = service.list_breached(actor_user_id="u1", as_of=far_future)
        assert len(breached) == 1
        with CustomerServiceUnitOfWork(cs_conn) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
        assert breached[0].id == sla.id

    def test_permission_denied(self, cs_conn):
        with pytest.raises(CRMPermissionDeniedError):
            SLAQueryService(cs_conn, _deny()).list_breached(actor_user_id="u1")
