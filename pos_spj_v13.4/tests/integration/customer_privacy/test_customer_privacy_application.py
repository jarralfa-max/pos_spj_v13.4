"""CRM-9 — Customer Privacy application tests (use cases + query services).

Covers happy path, permission-denied (fail closed), invalid state,
idempotency, rollback, audit, consent capture/request/confirm/withdraw,
communication preferences, the full privacy-request workflow, the
anonymization hot-authorization + SoD path (cross-bounded-context with
`customers`), and query-service scope.
"""

from __future__ import annotations

import pytest

from backend.application.customers.authorization import (
    CustomerAuthorizationPolicy,
    DenyAllCustomerPermissionCheckerForTests,
)
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.application.customer_privacy.queries.customer_communication_preference_query_service import (
    CustomerCommunicationPreferenceQueryService,
)
from backend.application.customer_privacy.queries.customer_consent_query_service import (
    CustomerConsentQueryService,
)
from backend.application.customer_privacy.queries.customer_privacy_request_query_service import (
    CustomerPrivacyRequestQueryService,
)
from backend.application.customer_privacy.use_cases.anonymize_customer_use_case import (
    AnonymizeCustomerUseCase,
)
from backend.application.customer_privacy.use_cases.communication_preference_use_cases import (
    SetCommunicationPreferenceUseCase,
)
from backend.application.customer_privacy.use_cases.consent_use_cases import (
    CaptureConsentUseCase,
    ConfirmConsentUseCase,
    MarkConsentNotRequiredUseCase,
    RequestConsentUseCase,
    WithdrawConsentUseCase,
)
from backend.application.customer_privacy.use_cases.privacy_request_use_cases import (
    CancelPrivacyRequestUseCase,
    CompletePrivacyRequestUseCase,
    CreatePrivacyRequestUseCase,
    RejectPrivacyRequestUseCase,
    StartProcessingPrivacyRequestUseCase,
    ValidatePrivacyRequestUseCase,
)
from backend.application.customer_privacy.use_cases.retention_policy_use_cases import (
    CreateDataRetentionPolicyUseCase,
)
from backend.domain.customer_privacy.exceptions import PrivacyRequestNotFoundError
from backend.domain.customers.exceptions import CustomerPermissionDeniedError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork
from backend.shared.ids import new_uuid


def _allow():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _deny():
    return CustomerAuthorizationPolicy(DenyAllCustomerPermissionCheckerForTests())


def _create_customer(conn, *, display_name="Restaurante El Sol", customer_type="INDIVIDUAL"):
    return CreateCustomerUseCase(_allow()).execute(
        conn, actor_user_id="u1", display_name=display_name, customer_type=customer_type,
        operation_id=new_uuid()).entity_id


class TestCaptureConsent:
    def test_happy_path(self, cp_conn):
        result = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="checkbox web", operation_id=new_uuid())
        assert result.success

    def test_permission_denied(self, cp_conn):
        result = CaptureConsentUseCase(_deny()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, cp_conn):
        op_id = new_uuid()
        first = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=op_id)
        second = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=op_id)
        assert first.entity_id == second.entity_id
        count = cp_conn.execute("SELECT COUNT(*) FROM customer_consents").fetchone()[0]
        assert count == 1

    def test_missing_evidence_is_validation_error(self, cp_conn):
        result = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="   ", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestRequestConfirmWithdrawConsent:
    def test_request_then_confirm(self, cp_conn):
        req_result = RequestConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="WHATSAPP",
            operation_id=new_uuid())
        assert req_result.success
        confirm_result = ConfirmConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", consent_id=req_result.entity_id,
            evidence_reference="respondió SI", operation_id=new_uuid())
        assert confirm_result.success

    def test_withdraw_requires_permission(self, cp_conn):
        capture = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid())
        result = WithdrawConsentUseCase(_deny()).execute(
            cp_conn, actor_user_id="u1", consent_id=capture.entity_id, reason="motivo",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_withdraw_requires_reason(self, cp_conn):
        capture = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid())
        result = WithdrawConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", consent_id=capture.entity_id, reason="",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_mark_not_required(self, cp_conn):
        result = MarkConsentNotRequiredUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="PROFILING",
            operation_id=new_uuid())
        assert result.success


class TestCommunicationPreference:
    def test_create_on_first_set(self, cp_conn):
        result = SetCommunicationPreferenceUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid(),
            allow_marketing=True)
        assert result.success
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            pref = uow.preferences.get_by_customer_id("cust-1")
        assert pref.allow_marketing is True

    def test_second_call_updates_existing_record(self, cp_conn):
        SetCommunicationPreferenceUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid(),
            allow_marketing=True)
        SetCommunicationPreferenceUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid(),
            allow_marketing=False, allow_reminders=False)
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            count = uow.connection.execute(
                "SELECT COUNT(*) FROM customer_communication_preferences").fetchone()[0]
            pref = uow.preferences.get_by_customer_id("cust-1")
        assert count == 1  # upsert, not a second row
        assert pref.allow_marketing is False
        assert pref.allow_reminders is False

    def test_permission_denied(self, cp_conn):
        result = SetCommunicationPreferenceUseCase(_deny()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestPrivacyRequestWorkflow:
    def test_full_generic_flow(self, cp_conn):
        create = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u-agente", customer_id="cust-1", request_type="ACCESS",
            operation_id=new_uuid())
        assert create.success
        request_id = create.entity_id
        assert ValidatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u-analista", request_id=request_id,
            operation_id=new_uuid()).success
        assert StartProcessingPrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u-analista", request_id=request_id,
            operation_id=new_uuid()).success
        assert CompletePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u-analista", request_id=request_id,
            operation_id=new_uuid()).success

    def test_idempotent_on_operation_id(self, cp_conn):
        op_id = new_uuid()
        first = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="ACCESS",
            operation_id=op_id)
        second = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="ACCESS",
            operation_id=op_id)
        assert first.entity_id == second.entity_id

    def test_reject_and_cancel(self, cp_conn):
        r1 = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="OPPOSITION",
            operation_id=new_uuid()).entity_id
        assert RejectPrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r1, operation_id=new_uuid(),
            reason="identidad no verificada").success

        r2 = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="OPPOSITION",
            operation_id=new_uuid()).entity_id
        assert CancelPrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r2, operation_id=new_uuid(),
            reason="cliente retiró la solicitud").success

    def test_generic_complete_rejects_anonymization_type(self, cp_conn):
        r = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="ANONYMIZATION",
            operation_id=new_uuid()).entity_id
        ValidatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        StartProcessingPrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        result = CompletePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_consent_withdrawal_type_withdraws_linked_consent(self, cp_conn):
        consent_id = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid()).entity_id
        r = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1",
            request_type="CONSENT_WITHDRAWAL", operation_id=new_uuid(),
            related_consent_id=consent_id).entity_id
        ValidatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        StartProcessingPrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        result = CompletePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id=r, operation_id=new_uuid())
        assert result.success
        with CustomerPrivacyUnitOfWork(cp_conn) as uow:
            consent = uow.consents.get(consent_id)
        assert consent.status.value == "WITHDRAWN"

    def test_missing_request_returns_not_found(self, cp_conn):
        result = ValidatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", request_id="does-not-exist", operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class TestAnonymizeCustomer:
    def _in_progress_anonymization_request(self, conn, *, logged_by="u-agente"):
        customer_id = _create_customer(conn)
        request_id = CreatePrivacyRequestUseCase(_allow()).execute(
            conn, actor_user_id=logged_by, customer_id=customer_id, request_type="ANONYMIZATION",
            operation_id=new_uuid()).entity_id
        ValidatePrivacyRequestUseCase(_allow()).execute(
            conn, actor_user_id="u-analista", request_id=request_id, operation_id=new_uuid())
        StartProcessingPrivacyRequestUseCase(_allow()).execute(
            conn, actor_user_id="u-analista", request_id=request_id, operation_id=new_uuid())
        return customer_id, request_id

    def test_same_authorizer_as_requester_denied(self, cp_and_customers_conn):
        _, request_id = self._in_progress_anonymization_request(
            cp_and_customers_conn, logged_by="u-agente")
        result = AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-agente", request_id=request_id,
            operation_id=new_uuid(), reason="motivo")
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_distinct_authorizer_succeeds_and_redacts_customer(self, cp_and_customers_conn):
        customer_id, request_id = self._in_progress_anonymization_request(
            cp_and_customers_conn, logged_by="u-agente")
        result = AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-director", request_id=request_id,
            operation_id=new_uuid(), reason="aprobado por dirección")
        assert result.success
        with CustomerUnitOfWork(cp_and_customers_conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.status.value == "ANONYMIZED"
        assert customer.display_name == "Cliente anonimizado"

    def test_legal_name_not_touched(self, cp_and_customers_conn):
        customer_id = CreateCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u1", display_name="El Sol SA de CV",
            customer_type="BUSINESS", legal_name="El Sol Sociedad Anonima de Capital Variable",
            operation_id=new_uuid()).entity_id
        request_id = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u-agente", customer_id=customer_id,
            request_type="ANONYMIZATION", operation_id=new_uuid()).entity_id
        ValidatePrivacyRequestUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u1", request_id=request_id,
            operation_id=new_uuid())
        StartProcessingPrivacyRequestUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u1", request_id=request_id,
            operation_id=new_uuid())
        AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-director", request_id=request_id,
            operation_id=new_uuid(), reason="aprobado")
        with CustomerUnitOfWork(cp_and_customers_conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.legal_name == "El Sol Sociedad Anonima de Capital Variable"

    def test_wrong_request_type_rejected(self, cp_and_customers_conn):
        customer_id = _create_customer(cp_and_customers_conn)
        request_id = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u-agente", customer_id=customer_id,
            request_type="ACCESS", operation_id=new_uuid()).entity_id
        result = AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-director", request_id=request_id,
            operation_id=new_uuid(), reason="motivo")
        assert not result.success and result.error_code == "VALIDATION"

    def test_wrong_status_rejected(self, cp_and_customers_conn):
        customer_id = _create_customer(cp_and_customers_conn)
        request_id = CreatePrivacyRequestUseCase(_allow()).execute(
            cp_and_customers_conn, actor_user_id="u-agente", customer_id=customer_id,
            request_type="ANONYMIZATION", operation_id=new_uuid()).entity_id
        # still RECEIVED, never validated/started
        result = AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-director", request_id=request_id,
            operation_id=new_uuid(), reason="motivo")
        assert not result.success and result.error_code == "VALIDATION"

    def test_marks_request_completed(self, cp_and_customers_conn):
        customer_id, request_id = self._in_progress_anonymization_request(
            cp_and_customers_conn, logged_by="u-agente")
        AnonymizeCustomerUseCase(_allow()).execute(
            cp_and_customers_conn, authorizer_user_id="u-director", request_id=request_id,
            operation_id=new_uuid(), reason="aprobado")
        with CustomerPrivacyUnitOfWork(cp_and_customers_conn) as uow:
            request = uow.requests.get(request_id)
            audit = uow.audit.list_for_request(request_id)
        assert request.status.value == "COMPLETED"
        anonymized_entries = [a for a in audit if a["action"] == "CUSTOMER_ANONYMIZED"]
        assert len(anonymized_entries) == 1
        assert anonymized_entries[0]["authorized_by_user_id"] == "u-director"


class TestRetentionPolicy:
    def test_create_requires_settings_manage(self, cp_conn):
        result = CreateDataRetentionPolicyUseCase(_deny()).execute(
            cp_conn, actor_user_id="u1", code="X", name="X", data_category="PERSONAL_DATA",
            retention_days=365, operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_create_happy_path(self, cp_conn):
        result = CreateDataRetentionPolicyUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", code="DEFAULT", name="Default",
            data_category="PERSONAL_DATA", retention_days=365, operation_id=new_uuid())
        assert result.success


class TestCustomerConsentQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return CustomerConsentQueryService(conn, CustomerAuthorizationPolicy(_Checker()))

    def test_is_active_true_after_capture(self, cp_conn):
        CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid())
        service = self._service(cp_conn, {CustomerPermissions.CONSENT_VIEW})
        assert service.is_active("cust-1", "MARKETING", actor_user_id="u1") is True

    def test_is_active_false_after_withdraw(self, cp_conn):
        consent_id = CaptureConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", consent_type="MARKETING",
            evidence_reference="x", operation_id=new_uuid()).entity_id
        WithdrawConsentUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", consent_id=consent_id, reason="motivo",
            operation_id=new_uuid())
        service = self._service(cp_conn, {CustomerPermissions.CONSENT_VIEW})
        assert service.is_active("cust-1", "MARKETING", actor_user_id="u1") is False

    def test_is_active_false_when_never_captured(self, cp_conn):
        service = self._service(cp_conn, {CustomerPermissions.CONSENT_VIEW})
        assert service.is_active("cust-1", "MARKETING", actor_user_id="u1") is False

    def test_permission_denied(self, cp_conn):
        service = self._service(cp_conn, set())
        with pytest.raises(CustomerPermissionDeniedError):
            service.list_for_customer("cust-1", actor_user_id="u1")


class TestCustomerPrivacyRequestQueryService:
    def test_get_missing_raises_not_found(self, cp_conn):
        service = CustomerPrivacyRequestQueryService(cp_conn, _allow())
        with pytest.raises(PrivacyRequestNotFoundError):
            service.get("does-not-exist", actor_user_id="u1")

    def test_list_for_customer(self, cp_conn):
        CreatePrivacyRequestUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", request_type="ACCESS",
            operation_id=new_uuid())
        service = CustomerPrivacyRequestQueryService(cp_conn, _allow())
        results = service.list_for_customer("cust-1", actor_user_id="u1")
        assert len(results) == 1


class TestCustomerCommunicationPreferenceQueryService:
    def test_get_returns_none_when_not_set(self, cp_conn):
        service = CustomerCommunicationPreferenceQueryService(cp_conn, _allow())
        assert service.get("cust-1", actor_user_id="u1") is None

    def test_get_returns_saved_preference(self, cp_conn):
        SetCommunicationPreferenceUseCase(_allow()).execute(
            cp_conn, actor_user_id="u1", customer_id="cust-1", operation_id=new_uuid(),
            allow_marketing=True)
        service = CustomerCommunicationPreferenceQueryService(cp_conn, _allow())
        pref = service.get("cust-1", actor_user_id="u1")
        assert pref.allow_marketing is True
