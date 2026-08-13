"""CRM-11 — Calidad/Duplicados/Fusión/Importación application tests:
permissions, SoD (merge proposer≠approver, sensitive-import submitter≠
approver), hot authorization, idempotent detection, and the merge
workflow's actual data resolution (contacts/addresses/tax profile).
"""

from __future__ import annotations

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_data_quality_query_service import (
    CustomerDataQualityQueryService,
)
from backend.application.customers.queries.customer_duplicate_query_service import (
    CustomerDuplicateQueryService,
)
from backend.application.customers.queries.customer_import_preview_query import (
    CustomerImportPreviewQuery,
)
from backend.application.customers.use_cases.address_use_cases import AddCustomerAddressUseCase
from backend.application.customers.use_cases.contact_use_cases import AddCustomerContactUseCase
from backend.application.customers.use_cases.data_quality_use_cases import (
    AcknowledgeDataQualityIssueUseCase,
    CorrectDataQualityIssueUseCase,
    DismissDataQualityIssueUseCase,
    RunCustomerDataQualityScanUseCase,
)
from backend.application.customers.use_cases.duplicate_use_cases import (
    ConfirmDuplicateCandidateUseCase,
    DetectDuplicateCandidatesUseCase,
    DismissDuplicateCandidateUseCase,
    ReviewDuplicateCandidateUseCase,
)
from backend.application.customers.use_cases.import_use_cases import (
    ApproveCustomerImportUseCase,
    ImportCustomersUseCase,
    RejectCustomerImportUseCase,
)
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.application.customers.use_cases.merge_use_cases import (
    ExecuteCustomerMergeUseCase,
    ProposeCustomerMergeUseCase,
    RejectCustomerMergeUseCase,
)
from backend.application.customers.use_cases.tax_profile_use_cases import (
    UpdateCustomerTaxProfileUseCase,
)
from backend.shared.ids import new_uuid


def _allow():
    return CustomerAuthorizationPolicy.permissive_for_tests()


class _DenyChecker:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


def _deny():
    return CustomerAuthorizationPolicy(_DenyChecker())


class _RecordingChecker:
    def __init__(self) -> None:
        self.checked: list[str] = []

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        self.checked.append(permission_code)
        return True


def _customer(conn, *, name="Restaurante El Sol", **kwargs) -> str:
    kwargs.setdefault("allow_duplicate", True)
    result = CreateCustomerUseCase(_allow()).execute(
        conn, actor_user_id="u1", display_name=name, operation_id=new_uuid(), **kwargs)
    assert result.success
    return result.entity_id


class TestDetectAndResolveDuplicates:
    def test_detects_matching_pair_by_name(self, cust_conn):
        a = _customer(cust_conn, name="Juan Perez Gomez")
        b = _customer(cust_conn, name="Juan Perez Gomez")
        result = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert result.success and len(result.data["candidate_ids"]) == 1

        candidates = CustomerDuplicateQueryService(cust_conn, _allow()).list_by_status(
            "DETECTED", actor_user_id="u1")
        assert len(candidates) == 1
        assert {candidates[0].customer_id_a, candidates[0].customer_id_b} == {a, b}

    def test_rerunning_detection_does_not_duplicate_candidates(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        _customer(cust_conn, name="Juan Perez Gomez")
        DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        second = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert second.data["candidate_ids"] == []

    def test_no_match_for_unrelated_customers(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        _customer(cust_conn, name="Empresa Distinta SA")
        result = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert result.data["candidate_ids"] == []

    def test_detect_requires_permission(self, cust_conn):
        result = DetectDuplicateCandidatesUseCase(_deny()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_review_confirm_dismiss_lifecycle(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        _customer(cust_conn, name="Juan Perez Gomez")
        detected = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        candidate_id = detected.data["candidate_ids"][0]

        reviewed = ReviewDuplicateCandidateUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", candidate_id=candidate_id, operation_id=new_uuid())
        assert reviewed.success

        confirmed = ConfirmDuplicateCandidateUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", candidate_id=candidate_id, operation_id=new_uuid())
        assert confirmed.success

        candidates = CustomerDuplicateQueryService(cust_conn, _allow()).list_by_status(
            "CONFIRMED_DUPLICATE", actor_user_id="u1")
        assert len(candidates) == 1

    def test_dismiss_requires_reason(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        _customer(cust_conn, name="Juan Perez Gomez")
        detected = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        candidate_id = detected.data["candidate_ids"][0]
        result = DismissDuplicateCandidateUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", candidate_id=candidate_id, reason="",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestCustomerMerge:
    def test_propose_requires_confirmed_candidate_when_given(self, cust_conn):
        a = _customer(cust_conn, name="Juan Perez Gomez")
        b = _customer(cust_conn, name="Juan Perez Gomez")
        detected = DetectDuplicateCandidatesUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        candidate_id = detected.data["candidate_ids"][0]

        result = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid(), duplicate_candidate_id=candidate_id)
        assert not result.success and result.error_code == "VALIDATION"

    def test_propose_without_candidate_ok(self, cust_conn):
        a = _customer(cust_conn, name="Cliente A")
        b = _customer(cust_conn, name="Cliente B")
        result = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid(), reason="mismo cliente detectado manualmente")
        assert result.success

    def test_execute_requires_distinct_authorizer(self, cust_conn):
        a = _customer(cust_conn, name="Cliente A")
        b = _customer(cust_conn, name="Cliente B")
        proposed = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-vendedor", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid())
        result = ExecuteCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-vendedor", merge_record_id=proposed.entity_id,
            operation_id=new_uuid(), reason="confirmado")
        assert not result.success
        assert result.error_code in ("PERMISSION_DENIED", "SOD_VIOLATION")

    def test_execute_resolves_contacts_addresses_tax_profile(self, cust_conn):
        a = _customer(cust_conn, name="Cliente Maestro")
        b = _customer(cust_conn, name="Cliente Fusionado")
        AddCustomerContactUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=b, first_name="Contacto B",
            operation_id=new_uuid())
        AddCustomerAddressUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=b,
            street="Calle Falsa 123", operation_id=new_uuid())
        UpdateCustomerTaxProfileUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=b, tax_identifier="XAXX010101000",
            operation_id=new_uuid())

        proposed = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-vendedor", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid())
        result = ExecuteCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-supervisor", merge_record_id=proposed.entity_id,
            operation_id=new_uuid(), reason="duplicado confirmado por supervisor")
        assert result.success

        contacts = cust_conn.execute(
            "SELECT COUNT(*) FROM customer_contacts WHERE customer_id=?", (a,)).fetchone()[0]
        assert contacts == 1
        addresses = cust_conn.execute(
            "SELECT COUNT(*) FROM customer_addresses WHERE customer_id=?", (a,)).fetchone()[0]
        assert addresses == 1
        tax = cust_conn.execute(
            "SELECT tax_identifier FROM customer_tax_profiles WHERE customer_id=?",
            (a,)).fetchone()
        assert tax is not None and tax[0] == "XAXX010101000"

        merged_status = cust_conn.execute(
            "SELECT status FROM customers WHERE id=?", (b,)).fetchone()[0]
        assert merged_status == "MERGED"

    def test_execute_keeps_master_tax_profile_when_both_have_one(self, cust_conn):
        a = _customer(cust_conn, name="Cliente Maestro")
        b = _customer(cust_conn, name="Cliente Fusionado")
        UpdateCustomerTaxProfileUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=a, tax_identifier="MASTER010101000",
            operation_id=new_uuid())
        UpdateCustomerTaxProfileUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=b, tax_identifier="MERGED010101000",
            operation_id=new_uuid())

        proposed = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-vendedor", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid())
        ExecuteCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-supervisor", merge_record_id=proposed.entity_id,
            operation_id=new_uuid(), reason="duplicado confirmado")

        tax = cust_conn.execute(
            "SELECT tax_identifier FROM customer_tax_profiles WHERE customer_id=?",
            (a,)).fetchone()
        assert tax[0] == "MASTER010101000"
        merged_tax_count = cust_conn.execute(
            "SELECT COUNT(*) FROM customer_tax_profiles WHERE customer_id=?", (b,)).fetchone()[0]
        assert merged_tax_count == 0

    def test_reject_merge(self, cust_conn):
        a = _customer(cust_conn, name="Cliente A")
        b = _customer(cust_conn, name="Cliente B")
        proposed = ProposeCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", master_customer_id=a, merged_customer_id=b,
            operation_id=new_uuid())
        result = RejectCustomerMergeUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", merge_record_id=proposed.entity_id,
            reason="no son el mismo cliente", operation_id=new_uuid())
        assert result.success
        merged_status = cust_conn.execute(
            "SELECT status FROM customers WHERE id=?", (b,)).fetchone()[0]
        assert merged_status == "ACTIVE"


class TestDataQualityScan:
    def test_scan_flags_incomplete_name_and_missing_address(self, cust_conn):
        _customer(cust_conn, name="Maria")
        result = RunCustomerDataQualityScanUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert result.success
        assert len(result.data["issue_ids"]) >= 2

    def test_rerunning_scan_does_not_duplicate_open_issues(self, cust_conn):
        _customer(cust_conn, name="Maria")
        RunCustomerDataQualityScanUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        second = RunCustomerDataQualityScanUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert second.data["issue_ids"] == []

    def test_scan_requires_permission(self, cust_conn):
        result = RunCustomerDataQualityScanUseCase(_deny()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_acknowledge_correct_lifecycle(self, cust_conn):
        _customer(cust_conn, name="Maria")
        scan = RunCustomerDataQualityScanUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        issue_id = scan.data["issue_ids"][0]

        acknowledged = AcknowledgeDataQualityIssueUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", issue_id=issue_id, operation_id=new_uuid())
        assert acknowledged.success

        corrected = CorrectDataQualityIssueUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", issue_id=issue_id, operation_id=new_uuid())
        assert corrected.success

        customer_id = _customer_id_of_issue(cust_conn, issue_id)
        open_issues = CustomerDataQualityQueryService(cust_conn, _allow()).list_open_for_customer(
            customer_id, actor_user_id="u1")
        assert all(i.id != issue_id for i in open_issues)

    def test_dismiss_requires_reason(self, cust_conn):
        _customer(cust_conn, name="Maria")
        scan = RunCustomerDataQualityScanUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", operation_id=new_uuid())
        issue_id = scan.data["issue_ids"][0]
        result = DismissDataQualityIssueUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", issue_id=issue_id, reason="", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


def _customer_id_of_issue(conn, issue_id: str) -> str:
    return conn.execute(
        "SELECT customer_id FROM customer_data_quality_issues WHERE id=?", (issue_id,)
    ).fetchone()[0]


class TestCustomerImport:
    def test_import_creates_and_tallies(self, cust_conn):
        rows = [
            {"display_name": "Cliente Importado Uno"},
            {"display_name": "Cliente Importado Dos"},
            {"display_name": ""},
        ]
        result = ImportCustomersUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", rows=rows, operation_id=new_uuid())
        assert result.success
        assert result.data["created"] == 2
        assert result.data["error"] == 1

    def test_import_flags_duplicate_rows(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        rows = [{"display_name": "Juan Perez Gomez"}]
        result = ImportCustomersUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", rows=rows, operation_id=new_uuid())
        assert result.success
        assert result.data["duplicate"] == 1
        assert result.data["created"] == 0

    def test_import_requires_rows(self, cust_conn):
        result = ImportCustomersUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", rows=[], operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_import_requires_permission(self, cust_conn):
        result = ImportCustomersUseCase(_deny()).execute(
            cust_conn, actor_user_id="u1", rows=[{"display_name": "X"}],
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_sensitive_import_defers_and_requires_distinct_approver(self, cust_conn):
        rows = [{"display_name": "Cliente Sensible"}]
        submitted = ImportCustomersUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-analista", rows=rows, operation_id=new_uuid(),
            is_sensitive=True)
        assert submitted.success
        # nothing written yet
        assert cust_conn.execute(
            "SELECT COUNT(*) FROM customers WHERE display_name='Cliente Sensible'"
        ).fetchone()[0] == 0

        same_user = ApproveCustomerImportUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-analista", batch_id=submitted.entity_id,
            operation_id=new_uuid())
        assert not same_user.success and same_user.error_code == "SOD_VIOLATION"

        approved = ApproveCustomerImportUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-supervisor", batch_id=submitted.entity_id,
            operation_id=new_uuid())
        assert approved.success
        assert approved.data["created"] == 1
        assert cust_conn.execute(
            "SELECT COUNT(*) FROM customers WHERE display_name='Cliente Sensible'"
        ).fetchone()[0] == 1

    def test_reject_sensitive_import(self, cust_conn):
        rows = [{"display_name": "Cliente Sensible"}]
        submitted = ImportCustomersUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-analista", rows=rows, operation_id=new_uuid(),
            is_sensitive=True)
        result = RejectCustomerImportUseCase(_allow()).execute(
            cust_conn, actor_user_id="u-supervisor", batch_id=submitted.entity_id,
            operation_id=new_uuid())
        assert result.success
        assert cust_conn.execute(
            "SELECT COUNT(*) FROM customers WHERE display_name='Cliente Sensible'"
        ).fetchone()[0] == 0

    def test_preview_reports_outcomes_without_writing(self, cust_conn):
        _customer(cust_conn, name="Juan Perez Gomez")
        rows = [{"display_name": "Juan Perez Gomez"}, {"display_name": "Cliente Nuevo"},
                {"display_name": ""}]
        previews = CustomerImportPreviewQuery(cust_conn, _allow()).preview(
            rows, actor_user_id="u1")
        outcomes = [p.outcome for p in previews]
        assert outcomes == ["DUPLICATE", "WOULD_CREATE", "ERROR"]
        assert cust_conn.execute(
            "SELECT COUNT(*) FROM customers WHERE display_name='Cliente Nuevo'"
        ).fetchone()[0] == 0
