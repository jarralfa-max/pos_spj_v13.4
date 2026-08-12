"""CRM-7 — Service Case domain unit tests: entity lifecycle,
ServiceCaseCode, ServiceCaseCategory, ServiceLevelPolicy,
ServiceLevelPolicyResolver, SLAInstance breach derivation,
ServiceCaseResolution, ServiceCaseEscalation. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.customer_service.entities.customer_service_case import CustomerServiceCase
from backend.domain.customer_service.entities.service_case_category import ServiceCaseCategory
from backend.domain.customer_service.entities.service_case_escalation import (
    ServiceCaseEscalation,
)
from backend.domain.customer_service.entities.service_case_resolution import (
    ServiceCaseResolution,
)
from backend.domain.customer_service.entities.service_level_policy import ServiceLevelPolicy
from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.domain.customer_service.enums import (
    EscalationReason,
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseStatus,
    ServiceCaseType,
    SLABreachStatus,
)
from backend.domain.customer_service.exceptions import (
    CustomerServiceDomainError,
    InvalidServiceCaseCategoryError,
    InvalidServiceCaseCodeError,
    InvalidServiceCaseResolutionError,
    InvalidServiceCaseStateError,
    InvalidServiceLevelPolicyError,
    InvalidSLAInstanceError,
)
from backend.domain.customer_service.policies.service_level_policy_resolver import (
    ServiceLevelPolicyResolver,
)
from backend.domain.customer_service.value_objects.service_case_code import ServiceCaseCode


def _case(**kwargs) -> CustomerServiceCase:
    return CustomerServiceCase.create(
        ServiceCaseCode.from_sequence(1), kwargs.pop("customer_id", "cust-1"),
        kwargs.pop("case_type", ServiceCaseType.COMPLAINT),
        kwargs.pop("subject", "Producto en mal estado"), **kwargs)


class TestCustomerServiceCaseLifecycle:
    def test_create_defaults_to_new(self):
        case = _case()
        assert case.status is ServiceCaseStatus.NEW

    def test_create_requires_subject(self):
        with pytest.raises(InvalidServiceCaseStateError):
            _case(subject="   ")

    def test_create_requires_customer_id(self):
        with pytest.raises(InvalidServiceCaseStateError):
            CustomerServiceCase.create(ServiceCaseCode.from_sequence(1), "", ServiceCaseType.OTHER,
                                       "x")

    def test_assign_owner_from_new_moves_to_assigned(self):
        case = _case()
        case.assign_owner("u1")
        assert case.status is ServiceCaseStatus.ASSIGNED
        assert case.assigned_user_id == "u1"

    def test_reassign_keeps_status_when_not_new(self):
        case = _case()
        case.assign_owner("u1")
        case.start_progress()
        case.assign_owner("u2")
        assert case.status is ServiceCaseStatus.IN_PROGRESS
        assert case.assigned_user_id == "u2"

    def test_full_happy_path_to_close(self):
        case = _case()
        case.assign_owner("u1")
        case.start_progress()
        case.wait_for_customer()
        case.resume()
        case.escalate()
        case.resolve()
        assert case.status is ServiceCaseStatus.RESOLVED
        assert case.resolved_at is not None
        case.close()
        assert case.status is ServiceCaseStatus.CLOSED
        assert case.is_terminal()

    def test_start_progress_only_from_assigned(self):
        with pytest.raises(InvalidServiceCaseStateError):
            _case().start_progress()

    def test_wait_for_customer_only_from_in_progress_or_escalated(self):
        case = _case()
        with pytest.raises(InvalidServiceCaseStateError):
            case.wait_for_customer()

    def test_resume_only_from_waiting(self):
        with pytest.raises(InvalidServiceCaseStateError):
            _case().resume()

    def test_escalate_is_re_escalatable(self):
        case = _case()
        case.assign_owner("u1")
        case.start_progress()
        case.escalate()
        case.escalate()  # re-escalation allowed
        assert case.status is ServiceCaseStatus.ESCALATED

    def test_cancel_requires_reason(self):
        case = _case()
        with pytest.raises(InvalidServiceCaseStateError):
            case.cancel("")
        case.cancel("cliente se retractó")
        assert case.status is ServiceCaseStatus.CANCELLED
        assert case.is_terminal()

    def test_close_only_from_resolved(self):
        with pytest.raises(InvalidServiceCaseStateError):
            _case().close()

    def test_reopen_from_closed_increments_reopen_count(self):
        case = _case()
        case.assign_owner("u1")
        case.start_progress()
        case.resolve()
        case.close()
        case.reopen("el cliente volvió a contactar")
        assert case.status is ServiceCaseStatus.IN_PROGRESS
        assert case.reopen_count == 1
        assert case.closed_at is None
        assert case.resolved_at is None

    def test_reopen_requires_reason(self):
        case = _case()
        case.assign_owner("u1")
        case.start_progress()
        case.resolve()
        with pytest.raises(InvalidServiceCaseStateError):
            case.reopen("")

    def test_terminal_case_rejects_further_transitions(self):
        case = _case()
        case.cancel("x")
        with pytest.raises(InvalidServiceCaseStateError):
            case.assign_owner("u1")


class TestServiceCaseCode:
    def test_from_sequence_formats_with_prefix_and_padding(self):
        assert str(ServiceCaseCode.from_sequence(42)) == "CASE-000042"

    def test_rejects_malformed_code(self):
        with pytest.raises(InvalidServiceCaseCodeError):
            ServiceCaseCode("NOT-A-CODE")


class TestServiceCaseCategory:
    def test_create_normalizes_code(self):
        category = ServiceCaseCategory.create("facturacion", "Facturación")
        assert category.code == "FACTURACION"

    def test_create_requires_name(self):
        with pytest.raises(InvalidServiceCaseCategoryError):
            ServiceCaseCategory.create("X", "")

    def test_deactivate(self):
        category = ServiceCaseCategory.create("X", "X")
        category.deactivate()
        assert category.active is False


class TestServiceCaseResolution:
    def test_create_requires_summary(self):
        with pytest.raises(InvalidServiceCaseResolutionError):
            ServiceCaseResolution.create("case-1", "   ", "u1")

    def test_create_requires_resolved_by(self):
        with pytest.raises(InvalidServiceCaseResolutionError):
            ServiceCaseResolution.create("case-1", "resuelto", "")


class TestServiceCaseEscalation:
    def test_create_requires_recipient(self):
        with pytest.raises(CustomerServiceDomainError):
            ServiceCaseEscalation.create("case-1", EscalationReason.CRITICAL_CASE, 1, "", "u1")

    def test_create_requires_level_at_least_one(self):
        with pytest.raises(CustomerServiceDomainError):
            ServiceCaseEscalation.create("case-1", EscalationReason.CRITICAL_CASE, 0, "u2", "u1")


class TestServiceLevelPolicy:
    def test_create_requires_positive_minutes(self):
        with pytest.raises(InvalidServiceLevelPolicyError):
            ServiceLevelPolicy.create("X", "X", 0, 100)

    def test_resolution_cannot_be_less_than_first_response(self):
        with pytest.raises(InvalidServiceLevelPolicyError):
            ServiceLevelPolicy.create("X", "X", 100, 50)

    def test_rejects_out_of_range_threshold(self):
        with pytest.raises(InvalidServiceLevelPolicyError):
            ServiceLevelPolicy.create("X", "X", 30, 100, at_risk_threshold_pct=150)

    def test_matches_wildcard_policy_matches_everything(self):
        policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
        assert policy.matches(case_type=ServiceCaseType.COMPLAINT,
                              priority=ServiceCasePriority.LOW, origin_branch_id=None,
                              channel=ServiceCaseChannel.EMAIL)
        assert policy.specificity() == 0

    def test_matches_specific_policy_requires_exact_match(self):
        policy = ServiceLevelPolicy.create("HIGH", "Alta", 15, 120,
                                           priority=ServiceCasePriority.HIGH)
        assert not policy.matches(case_type=ServiceCaseType.COMPLAINT,
                                  priority=ServiceCasePriority.LOW, origin_branch_id=None,
                                  channel=ServiceCaseChannel.EMAIL)
        assert policy.specificity() == 1


class TestServiceLevelPolicyResolver:
    def setup_method(self):
        self.resolver = ServiceLevelPolicyResolver()

    def test_prefers_most_specific_match(self):
        general = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
        specific = ServiceLevelPolicy.create("HIGH", "Alta", 15, 120,
                                             priority=ServiceCasePriority.HIGH)
        picked = self.resolver.resolve(
            [general, specific], case_type=ServiceCaseType.COMPLAINT,
            priority=ServiceCasePriority.HIGH, origin_branch_id=None,
            channel=ServiceCaseChannel.EMAIL)
        assert picked.code == "HIGH"

    def test_returns_none_when_nothing_matches(self):
        specific = ServiceLevelPolicy.create("HIGH", "Alta", 15, 120,
                                             priority=ServiceCasePriority.HIGH)
        picked = self.resolver.resolve(
            [specific], case_type=ServiceCaseType.COMPLAINT, priority=ServiceCasePriority.LOW,
            origin_branch_id=None, channel=ServiceCaseChannel.EMAIL)
        assert picked is None

    def test_ignores_inactive_policies(self):
        policy = ServiceLevelPolicy.create("DEFAULT", "Default", 60, 480)
        policy.deactivate()
        picked = self.resolver.resolve(
            [policy], case_type=ServiceCaseType.COMPLAINT, priority=ServiceCasePriority.LOW,
            origin_branch_id=None, channel=ServiceCaseChannel.EMAIL)
        assert picked is None


class TestSLAInstance:
    def _sla(self, **kwargs):
        return SLAInstance.create(
            kwargs.pop("case_id", "case-1"), kwargs.pop("policy_id", "policy-1"),
            kwargs.pop("first_response_minutes", 30), kwargs.pop("resolution_minutes", 120),
            **kwargs)

    def test_create_requires_case_id(self):
        with pytest.raises(InvalidSLAInstanceError):
            SLAInstance.create("", "policy-1", 30, 120)

    def test_record_first_response_twice_fails(self):
        sla = self._sla()
        sla.record_first_response()
        with pytest.raises(InvalidSLAInstanceError):
            sla.record_first_response()

    def test_record_resolution_twice_fails(self):
        sla = self._sla()
        sla.record_resolution()
        with pytest.raises(InvalidSLAInstanceError):
            sla.record_resolution()

    def test_bump_escalation_increments_and_returns_level(self):
        sla = self._sla()
        assert sla.bump_escalation() == 1
        assert sla.bump_escalation() == 2

    def test_effective_breach_status_on_time_early(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sla = self._sla(reference_time=base.isoformat(timespec="seconds"))
        as_of = (base + timedelta(minutes=10)).isoformat(timespec="seconds")
        assert sla.effective_breach_status(as_of=as_of) is SLABreachStatus.ON_TIME

    def test_effective_breach_status_at_risk_near_threshold(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sla = self._sla(reference_time=base.isoformat(timespec="seconds"),
                        at_risk_threshold_pct=80)
        as_of = (base + timedelta(minutes=100)).isoformat(timespec="seconds")  # 100/120=83%
        assert sla.effective_breach_status(as_of=as_of) is SLABreachStatus.AT_RISK

    def test_effective_breach_status_breached_after_due(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sla = self._sla(reference_time=base.isoformat(timespec="seconds"))
        as_of = (base + timedelta(minutes=200)).isoformat(timespec="seconds")
        assert sla.effective_breach_status(as_of=as_of) is SLABreachStatus.BREACHED

    def test_effective_breach_status_paused(self):
        sla = self._sla()
        sla.pause()
        assert sla.effective_breach_status() is SLABreachStatus.PAUSED

    def test_effective_breach_status_completed_after_resolution(self):
        sla = self._sla()
        sla.record_resolution()
        assert sla.effective_breach_status() is SLABreachStatus.COMPLETED

    def test_resume_clears_paused(self):
        sla = self._sla()
        sla.pause()
        sla.resume()
        assert sla.paused is False
