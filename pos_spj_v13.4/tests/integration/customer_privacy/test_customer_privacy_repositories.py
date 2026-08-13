"""CRM-9 — Consent/Preference/PrivacyRequest/RetentionPolicy repository
round-trips."""

from __future__ import annotations

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
from backend.domain.customer_privacy.enums import ConsentType, PrivacyRequestType
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class TestCustomerConsentRepository:
    def test_save_and_get_latest(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            consent = CustomerConsent.capture(
                "cust-1", ConsentType.MARKETING, evidence_reference="checkbox web",
                operation_id="op-1")
            uow.consents.save(consent, operation_id="op-1")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            latest = uow2.consents.get_latest("cust-1", "MARKETING")
            assert latest.status.value == "GRANTED"

    def test_get_by_operation_id_is_idempotency_lookup(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            consent = CustomerConsent.capture(
                "cust-1", ConsentType.MARKETING, evidence_reference="x", operation_id="op-dup")
            uow.consents.save(consent, operation_id="op-dup")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            found = uow2.consents.get_by_operation_id("op-dup")
            assert found is not None and found.id == consent.id

    def test_append_only_history_preserved_on_recapture(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            first = CustomerConsent.capture(
                "cust-1", ConsentType.MARKETING, evidence_reference="v1", operation_id="op-1")
            uow.consents.save(first, operation_id="op-1")
            first.withdraw("retiro inicial")
            uow.consents.update(first)
            second = CustomerConsent.capture(
                "cust-1", ConsentType.MARKETING, evidence_reference="v2", operation_id="op-2")
            uow.consents.save(second, operation_id="op-2")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            history = uow2.consents.list_for_customer("cust-1")
            latest = uow2.consents.get_latest("cust-1", "MARKETING")
        assert len(history) == 2
        assert latest.id == second.id
        assert latest.status.value == "GRANTED"

    def test_update_persists_withdrawal(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            consent = CustomerConsent.capture(
                "cust-1", ConsentType.MARKETING, evidence_reference="x", operation_id="op-1")
            uow.consents.save(consent, operation_id="op-1")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            consent = uow2.consents.get(consent.id)
            consent.withdraw("motivo")
            uow2.consents.update(consent)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow3:
            reloaded = uow3.consents.get(consent.id)
            assert reloaded.status.value == "WITHDRAWN"

    def test_rollback_on_exception_discards_all_writes(self, cp_conn):
        try:
            with CustomerPrivacyUnitOfWork(cp_conn) as uow:
                consent = CustomerConsent.capture(
                    "cust-1", ConsentType.MARKETING, evidence_reference="x", operation_id="op-1")
                uow.consents.save(consent, operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = cp_conn.execute("SELECT COUNT(*) FROM customer_consents").fetchone()[0]
        assert count == 0


class TestCustomerCommunicationPreferenceRepository:
    def test_save_and_get_by_customer_id(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            pref = CustomerCommunicationPreference.create("cust-1")
            uow.preferences.save(pref)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            fetched = uow2.preferences.get_by_customer_id("cust-1")
            assert fetched.preferred_channel.value == "WHATSAPP"

    def test_update_persists_flags(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            pref = CustomerCommunicationPreference.create("cust-1")
            uow.preferences.save(pref)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            pref = uow2.preferences.get_by_customer_id("cust-1")
            pref.update(updated_by_user_id="u1", allow_marketing=True, allow_promotions=True)
            uow2.preferences.update(pref)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow3:
            reloaded = uow3.preferences.get_by_customer_id("cust-1")
            assert reloaded.allow_marketing is True
            assert reloaded.allow_promotions is True


class TestCustomerPrivacyRequestRepository:
    def test_save_and_get(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            request = CustomerPrivacyRequest.create(
                uow.requests.next_code(), "cust-1", PrivacyRequestType.ACCESS,
                operation_id="op-1")
            uow.requests.save(request, operation_id="op-1")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            fetched = uow2.requests.get(request.id)
            assert str(fetched.code) == "PRIV-000001"

    def test_next_code_increments(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            r1 = CustomerPrivacyRequest.create(
                uow.requests.next_code(), "cust-1", PrivacyRequestType.ACCESS,
                operation_id="op-1")
            uow.requests.save(r1, operation_id="op-1")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            r2 = CustomerPrivacyRequest.create(
                uow2.requests.next_code(), "cust-1", PrivacyRequestType.EXPORT,
                operation_id="op-2")
            uow2.requests.save(r2, operation_id="op-2")
        assert str(r1.code) == "PRIV-000001"
        assert str(r2.code) == "PRIV-000002"

    def test_update_persists_status(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            request = CustomerPrivacyRequest.create(
                uow.requests.next_code(), "cust-1", PrivacyRequestType.ACCESS,
                operation_id="op-1")
            uow.requests.save(request, operation_id="op-1")
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            request = uow2.requests.get(request.id)
            request.validate("u-analista")
            uow2.requests.update(request)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow3:
            reloaded = uow3.requests.get(request.id)
            assert reloaded.status.value == "VALIDATING"

    def test_list_by_status(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            r1 = CustomerPrivacyRequest.create(
                uow.requests.next_code(), "cust-1", PrivacyRequestType.ACCESS,
                operation_id="op-1")
            uow.requests.save(r1, operation_id="op-1")
            r2 = CustomerPrivacyRequest.create(
                uow.requests.next_code(), "cust-2", PrivacyRequestType.EXPORT,
                operation_id="op-2")
            uow.requests.save(r2, operation_id="op-2")
            r2.validate("u1")
            uow.requests.update(r2)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            received = uow2.requests.list_by_status("RECEIVED")
            validating = uow2.requests.list_by_status("VALIDATING")
        assert [r.id for r in received] == [r1.id]
        assert [r.id for r in validating] == [r2.id]


class TestCustomerDataRetentionPolicyRepository:
    def test_save_and_list_active(self, cp_conn):
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            policy = CustomerDataRetentionPolicy.create(
                "DEFAULT", "Default", "PERSONAL_DATA", 365)
            uow.retention_policies.save(policy)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow2:
            active = uow2.retention_policies.list_active()
            assert [p.id for p in active] == [policy.id]
