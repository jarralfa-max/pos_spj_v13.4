"""CRM-8 — Customer Credit domain unit tests: CustomerCreditProfile
lifecycle, CreditSaleEligibilityPolicy. Pure domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.domain.customer_credit.enums import CreditProfileStatus, CreditRiskLevel
from backend.domain.customer_credit.exceptions import InvalidCustomerCreditStateError
from backend.domain.customer_credit.policies.credit_sale_eligibility_policy import (
    CreditSaleEligibilityPolicy,
)


def _profile(**kwargs) -> CustomerCreditProfile:
    return CustomerCreditProfile.request(
        kwargs.pop("customer_id", "cust-1"), kwargs.pop("requested_by_user_id", "u-vendedor"),
        **kwargs)


class TestCustomerCreditProfileLifecycle:
    def test_request_defaults_to_pending_approval(self):
        profile = _profile()
        assert profile.status is CreditProfileStatus.PENDING_APPROVAL
        assert profile.version == 1

    def test_request_requires_customer_id(self):
        with pytest.raises(InvalidCustomerCreditStateError):
            CustomerCreditProfile.request("", "u1")

    def test_request_requires_requester(self):
        with pytest.raises(InvalidCustomerCreditStateError):
            CustomerCreditProfile.request("cust-1", "")

    def test_request_rejects_negative_payment_terms(self):
        with pytest.raises(InvalidCustomerCreditStateError):
            _profile(payment_terms_days=-1)

    def test_credit_limit_rejects_float(self):
        with pytest.raises(InvalidCustomerCreditStateError):
            _profile(requested_limit=1000.5)

    def test_review_moves_to_under_review_and_bumps_version(self):
        profile = _profile()
        profile.review(risk_level=CreditRiskLevel.LOW)
        assert profile.status is CreditProfileStatus.UNDER_REVIEW
        assert profile.risk_level is CreditRiskLevel.LOW
        assert profile.version == 2

    def test_review_only_from_pending_approval(self):
        with pytest.raises(InvalidCustomerCreditStateError):
            profile = _profile()
            profile.status = CreditProfileStatus.AUTHORIZED
            profile.review()

    def test_approve_requires_under_review(self):
        profile = _profile()
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.approve("u-gerente")

    def test_approve_requires_positive_limit(self):
        profile = _profile(requested_limit="0")
        profile.review()
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.approve("u-gerente")

    def test_approve_sets_authorized_fields(self):
        profile = _profile()
        profile.review()
        profile.approve("u-gerente", credit_limit="10000", payment_terms_days=30,
                        risk_level=CreditRiskLevel.LOW)
        assert profile.status is CreditProfileStatus.AUTHORIZED
        assert profile.credit_limit == Decimal("10000")
        assert profile.payment_terms_days == 30
        assert profile.authorized_by_user_id == "u-gerente"
        assert profile.authorized_at is not None

    def test_reject_requires_reason_and_closes(self):
        profile = _profile()
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.reject("")
        profile.reject("documentación insuficiente")
        assert profile.status is CreditProfileStatus.CLOSED
        assert profile.close_reason == "documentación insuficiente"

    def test_update_limit_only_when_authorized(self):
        profile = _profile()
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.update_limit("5000", authorized_by_user_id="u1")

    def test_update_limit_rejects_non_positive(self):
        profile = _profile()
        profile.review()
        profile.approve("u-gerente", credit_limit="10000")
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.update_limit("0", authorized_by_user_id="u-gerente")

    def test_suspend_block_reopen_cycle(self):
        profile = _profile()
        profile.review()
        profile.approve("u-gerente", credit_limit="10000")
        profile.suspend("pago atrasado")
        assert profile.status is CreditProfileStatus.SUSPENDED
        profile.block("cobranza")
        assert profile.status is CreditProfileStatus.BLOCKED
        profile.reopen("cliente regularizó pagos")
        assert profile.status is CreditProfileStatus.AUTHORIZED
        assert profile.suspended_at is None
        assert profile.blocked_at is None

    def test_close_requires_reason(self):
        profile = _profile()
        profile.review()
        profile.approve("u-gerente", credit_limit="10000")
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.close("")
        profile.close("cliente cerró cuenta")
        assert profile.status is CreditProfileStatus.CLOSED
        assert profile.is_terminal()

    def test_terminal_profile_rejects_further_transitions(self):
        profile = _profile()
        profile.reject("x")
        with pytest.raises(InvalidCustomerCreditStateError):
            profile.review()

    def test_is_usable_for_credit_sale(self):
        profile = _profile()
        assert not profile.is_usable_for_credit_sale()
        profile.review()
        profile.approve("u-gerente", credit_limit="10000")
        assert profile.is_usable_for_credit_sale()


class TestCreditSaleEligibilityPolicy:
    def setup_method(self):
        self.policy = CreditSaleEligibilityPolicy()

    def _authorized_profile(self, limit="10000"):
        profile = _profile()
        profile.review()
        profile.approve("u-gerente", credit_limit=limit)
        return profile

    def test_eligible_when_all_rules_pass(self):
        profile = self._authorized_profile()
        result = self.policy.evaluate(
            profile, amount=Decimal("1000"), is_public_customer=False,
            available_credit=Decimal("5000"), documents_current=True, branch_allowed=True)
        assert result.eligible
        assert result.violations == ()

    def test_public_customer_never_eligible(self):
        profile = self._authorized_profile()
        result = self.policy.evaluate(
            profile, amount=Decimal("100"), is_public_customer=True,
            available_credit=Decimal("5000"), documents_current=True, branch_allowed=True)
        assert not result.eligible
        assert any("público" in v for v in result.violations)

    def test_no_profile_is_a_violation(self):
        result = self.policy.evaluate(
            None, amount=Decimal("100"), is_public_customer=False,
            available_credit=Decimal("0"), documents_current=True, branch_allowed=True)
        assert not result.eligible
        assert len(result.violations) >= 1

    def test_unauthorized_status_is_a_violation(self):
        profile = _profile()  # still PENDING_APPROVAL
        result = self.policy.evaluate(
            profile, amount=Decimal("100"), is_public_customer=False,
            available_credit=Decimal("5000"), documents_current=True, branch_allowed=True)
        assert not result.eligible
        assert any("autorizado" in v for v in result.violations)

    def test_insufficient_available_credit_is_a_violation(self):
        profile = self._authorized_profile()
        result = self.policy.evaluate(
            profile, amount=Decimal("6000"), is_public_customer=False,
            available_credit=Decimal("5000"), documents_current=True, branch_allowed=True)
        assert not result.eligible
        assert any("disponible" in v for v in result.violations)

    def test_stale_documents_is_a_violation(self):
        profile = self._authorized_profile()
        result = self.policy.evaluate(
            profile, amount=Decimal("100"), is_public_customer=False,
            available_credit=Decimal("5000"), documents_current=False, branch_allowed=True)
        assert not result.eligible
        assert any("documentos" in v for v in result.violations)

    def test_branch_not_allowed_is_a_violation(self):
        profile = self._authorized_profile()
        result = self.policy.evaluate(
            profile, amount=Decimal("100"), is_public_customer=False,
            available_credit=Decimal("5000"), documents_current=True, branch_allowed=False)
        assert not result.eligible
        assert any("sucursal" in v for v in result.violations)

    def test_multiple_violations_all_reported(self):
        result = self.policy.evaluate(
            None, amount=Decimal("0"), is_public_customer=True,
            available_credit=Decimal("0"), documents_current=False, branch_allowed=False)
        assert not result.eligible
        assert len(result.violations) >= 5
