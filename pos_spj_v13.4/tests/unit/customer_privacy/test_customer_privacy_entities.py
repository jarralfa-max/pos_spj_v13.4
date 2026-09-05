"""CRM-9 — Customer Privacy domain unit tests: CustomerConsent,
CustomerCommunicationPreference, CustomerPrivacyRequest,
CustomerDataRetentionPolicy, DataRetentionPolicyResolver. Pure domain — no
DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.customer_privacy.entities.customer_communication_preference import (
    CustomerCommunicationPreference,
)
from backend.domain.customer_privacy.entities.customer_consent import CustomerConsent
from backend.domain.customer_privacy.entities.customer_data_retention_policy import (
    CustomerDataRetentionPolicy,
)
from backend.domain.customer_privacy.entities.customer_privacy_request import (
    CustomerPrivacyRequest,
)
from backend.domain.customer_privacy.enums import (
    ConsentChannel,
    ConsentStatus,
    ConsentType,
    PreferredChannel,
    PrivacyRequestStatus,
    PrivacyRequestType,
)
from backend.domain.customer_privacy.exceptions import (
    CustomerPrivacyDomainError,
    InvalidCustomerConsentStateError,
    InvalidDataRetentionPolicyError,
    InvalidPrivacyRequestCodeError,
    InvalidPrivacyRequestStateError,
)
from backend.domain.customer_privacy.policies.data_retention_policy_resolver import (
    DataRetentionPolicyResolver,
)
from backend.domain.customer_privacy.value_objects.privacy_request_code import (
    PrivacyRequestCode,
)
from backend.domain.customers.enums import CustomerType


def _iso(delta_days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat(
        timespec="seconds")


class TestCustomerConsent:
    def test_capture_requires_evidence_reference(self):
        with pytest.raises(InvalidCustomerConsentStateError):
            CustomerConsent.capture("cust-1", ConsentType.MARKETING, evidence_reference="   ")

    def test_capture_grants_directly(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="checkbox web")
        assert consent.status is ConsentStatus.GRANTED
        assert consent.granted_at is not None

    def test_request_then_confirm(self):
        consent = CustomerConsent.request("cust-1", ConsentType.WHATSAPP)
        assert consent.status is ConsentStatus.PENDING
        consent.confirm(evidence_reference="respuesta SI por WhatsApp")
        assert consent.status is ConsentStatus.GRANTED

    def test_confirm_requires_evidence(self):
        consent = CustomerConsent.request("cust-1", ConsentType.WHATSAPP)
        with pytest.raises(InvalidCustomerConsentStateError):
            consent.confirm(evidence_reference="")

    def test_confirm_only_from_pending(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="x")
        with pytest.raises(InvalidCustomerConsentStateError):
            consent.confirm(evidence_reference="y")

    def test_withdraw_requires_reason(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="x")
        with pytest.raises(InvalidCustomerConsentStateError):
            consent.withdraw("")
        consent.withdraw("cliente solicitó baja")
        assert consent.status is ConsentStatus.WITHDRAWN

    def test_withdraw_only_from_granted(self):
        consent = CustomerConsent.request("cust-1", ConsentType.WHATSAPP)
        with pytest.raises(InvalidCustomerConsentStateError):
            consent.withdraw("motivo")

    def test_mark_not_required(self):
        consent = CustomerConsent.mark_not_required("cust-1", ConsentType.PROFILING)
        assert consent.status is ConsentStatus.NOT_REQUIRED

    def test_decline_goes_straight_to_withdrawn_without_prior_grant(self):
        """WA-14: un cliente puede rechazar un consentimiento que nunca
        había otorgado (p. ej. "BAJA" por WhatsApp la primera vez que
        escribe)."""
        consent = CustomerConsent.decline(
            "cust-1", ConsentType.WHATSAPP, reason="Cliente solicitó baja vía WhatsApp")
        assert consent.status is ConsentStatus.WITHDRAWN
        assert consent.withdrawn_at is not None
        assert consent.granted_at is None

    def test_decline_requires_reason(self):
        with pytest.raises(InvalidCustomerConsentStateError):
            CustomerConsent.decline("cust-1", ConsentType.WHATSAPP, reason="   ")

    def test_decline_requires_customer_id(self):
        with pytest.raises(InvalidCustomerConsentStateError):
            CustomerConsent.decline("", ConsentType.WHATSAPP, reason="motivo")

    def test_effective_status_expired_derivation(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="x", expires_at=_iso(-1))
        assert consent.effective_status() is ConsentStatus.EXPIRED
        assert consent.status is ConsentStatus.GRANTED  # never persisted as EXPIRED

    def test_effective_status_not_expired_when_future(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="x", expires_at=_iso(5))
        assert consent.effective_status() is ConsentStatus.GRANTED

    def test_is_active(self):
        consent = CustomerConsent.capture(
            "cust-1", ConsentType.MARKETING, evidence_reference="x")
        assert consent.is_active()
        consent.withdraw("motivo")
        assert not consent.is_active()


class TestCustomerCommunicationPreference:
    def test_create_requires_customer_id(self):
        with pytest.raises(CustomerPrivacyDomainError):
            CustomerCommunicationPreference.create("")

    def test_create_defaults(self):
        pref = CustomerCommunicationPreference.create("cust-1")
        assert pref.preferred_channel is PreferredChannel.WHATSAPP
        assert pref.allow_transactional is True
        assert pref.allow_marketing is False

    def test_update_requires_actor(self):
        pref = CustomerCommunicationPreference.create("cust-1")
        with pytest.raises(CustomerPrivacyDomainError):
            pref.update(updated_by_user_id="")

    def test_update_applies_only_provided_fields(self):
        pref = CustomerCommunicationPreference.create("cust-1")
        pref.update(updated_by_user_id="u1", allow_marketing=True)
        assert pref.allow_marketing is True
        assert pref.preferred_channel is PreferredChannel.WHATSAPP  # untouched


class TestPrivacyRequestCode:
    def test_from_sequence_formats_with_prefix_and_padding(self):
        assert str(PrivacyRequestCode.from_sequence(7)) == "PRIV-000007"

    def test_rejects_malformed_code(self):
        with pytest.raises(InvalidPrivacyRequestCodeError):
            PrivacyRequestCode("NOT-A-CODE")


class TestCustomerPrivacyRequest:
    def _request(self, **kwargs):
        request_type = kwargs.pop("request_type", PrivacyRequestType.ACCESS)
        return CustomerPrivacyRequest.create(
            PrivacyRequestCode.from_sequence(1), kwargs.pop("customer_id", "cust-1"),
            request_type, **kwargs)

    def test_create_requires_customer_id(self):
        with pytest.raises(InvalidPrivacyRequestStateError):
            CustomerPrivacyRequest.create(
                PrivacyRequestCode.from_sequence(1), "", PrivacyRequestType.ACCESS)

    def test_consent_withdrawal_requires_related_consent_id(self):
        with pytest.raises(InvalidPrivacyRequestStateError):
            self._request(request_type=PrivacyRequestType.CONSENT_WITHDRAWAL)
        req = self._request(request_type=PrivacyRequestType.CONSENT_WITHDRAWAL,
                            related_consent_id="consent-1")
        assert req.related_consent_id == "consent-1"

    def test_full_happy_path(self):
        req = self._request()
        req.validate("u-analista")
        assert req.status is PrivacyRequestStatus.VALIDATING
        req.start_processing("u-analista")
        assert req.status is PrivacyRequestStatus.IN_PROGRESS
        req.complete("acceso entregado")
        assert req.status is PrivacyRequestStatus.COMPLETED
        assert req.is_terminal()

    def test_reject_requires_reason(self):
        req = self._request()
        with pytest.raises(InvalidPrivacyRequestStateError):
            req.reject("")
        req.reject("identidad no verificada")
        assert req.status is PrivacyRequestStatus.REJECTED

    def test_cancel_requires_reason(self):
        req = self._request()
        with pytest.raises(InvalidPrivacyRequestStateError):
            req.cancel("")
        req.cancel("cliente retiró la solicitud")
        assert req.status is PrivacyRequestStatus.CANCELLED

    def test_terminal_request_rejects_further_transitions(self):
        req = self._request()
        req.cancel("x")
        with pytest.raises(InvalidPrivacyRequestStateError):
            req.validate("u1")

    def test_requires_anonymization_workflow(self):
        access_req = self._request(request_type=PrivacyRequestType.ACCESS)
        anon_req = self._request(request_type=PrivacyRequestType.ANONYMIZATION)
        cancel_req = self._request(request_type=PrivacyRequestType.CANCELLATION)
        assert not access_req.requires_anonymization_workflow()
        assert anon_req.requires_anonymization_workflow()
        assert cancel_req.requires_anonymization_workflow()

    def test_complete_only_from_in_progress(self):
        req = self._request()
        with pytest.raises(InvalidPrivacyRequestStateError):
            req.complete()


class TestCustomerDataRetentionPolicy:
    def test_create_requires_positive_retention_days(self):
        with pytest.raises(InvalidDataRetentionPolicyError):
            CustomerDataRetentionPolicy.create("X", "X", "PERSONAL_DATA", 0)

    def test_matches_wildcard(self):
        policy = CustomerDataRetentionPolicy.create("DEFAULT", "Default", "PERSONAL_DATA", 365)
        assert policy.matches(data_category="PERSONAL_DATA", customer_type=CustomerType.BUSINESS)
        assert policy.specificity() == 0

    def test_matches_specific_customer_type(self):
        policy = CustomerDataRetentionPolicy.create(
            "FISCAL", "Fiscal", "FINANCIAL_RECORDS", 1825, customer_type=CustomerType.BUSINESS)
        assert not policy.matches(data_category="FINANCIAL_RECORDS",
                                  customer_type=CustomerType.INDIVIDUAL)
        assert policy.specificity() == 1

    def test_deactivate(self):
        policy = CustomerDataRetentionPolicy.create("X", "X", "PERSONAL_DATA", 30)
        policy.deactivate()
        assert policy.active is False


class TestDataRetentionPolicyResolver:
    def setup_method(self):
        self.resolver = DataRetentionPolicyResolver()

    def test_prefers_most_specific_match(self):
        general = CustomerDataRetentionPolicy.create("DEFAULT", "Default", "PERSONAL_DATA", 365)
        specific = CustomerDataRetentionPolicy.create(
            "FISCAL", "Fiscal", "PERSONAL_DATA", 1825, customer_type=CustomerType.BUSINESS)
        picked = self.resolver.resolve(
            [general, specific], data_category="PERSONAL_DATA",
            customer_type=CustomerType.BUSINESS)
        assert picked.code == "FISCAL"

    def test_returns_none_when_nothing_matches(self):
        policy = CustomerDataRetentionPolicy.create(
            "FISCAL", "Fiscal", "FINANCIAL_RECORDS", 1825, customer_type=CustomerType.BUSINESS)
        picked = self.resolver.resolve(
            [policy], data_category="PERSONAL_DATA", customer_type=CustomerType.INDIVIDUAL)
        assert picked is None

    def test_ignores_inactive_policies(self):
        policy = CustomerDataRetentionPolicy.create("DEFAULT", "Default", "PERSONAL_DATA", 365)
        policy.deactivate()
        picked = self.resolver.resolve([policy], data_category="PERSONAL_DATA")
        assert picked is None
