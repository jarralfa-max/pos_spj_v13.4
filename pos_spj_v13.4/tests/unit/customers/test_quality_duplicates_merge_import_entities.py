"""CRM-11 — Calidad/Duplicados/Fusión/Importación domain unit tests:
CustomerDuplicateCandidate, CustomerMergeRecord, CustomerDataQualityIssue,
CustomerImportBatch. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.application.customers.services.customer_data_quality_service import (
    CustomerDataQualityService,
)
from backend.domain.customers.entities.customer_data_quality_issue import (
    CustomerDataQualityIssue,
)
from backend.domain.customers.entities.customer_duplicate_candidate import (
    CustomerDuplicateCandidate,
)
from backend.domain.customers.entities.customer_import_batch import CustomerImportBatch
from backend.domain.customers.entities.customer_merge_record import CustomerMergeRecord
from backend.domain.customers.enums import DataQualityRuleCode, ImportBatchStatus
from backend.domain.customers.exceptions import (
    InvalidCustomerImportError,
    InvalidCustomerMergeStateError,
    InvalidDataQualityIssueStateError,
    InvalidDuplicateCandidateStateError,
)


class TestCustomerDuplicateCandidate:
    def test_detect_requires_distinct_customers(self):
        with pytest.raises(InvalidDuplicateCandidateStateError):
            CustomerDuplicateCandidate.detect("cust-1", "cust-1", ("Mismo RFC",))

    def test_detect_requires_reasons(self):
        with pytest.raises(InvalidDuplicateCandidateStateError):
            CustomerDuplicateCandidate.detect("cust-1", "cust-2", ())

    def test_full_lifecycle_to_confirmed(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        candidate.start_review("u1")
        candidate.confirm()
        assert candidate.status.value == "CONFIRMED_DUPLICATE"

    def test_confirm_requires_under_review(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        with pytest.raises(InvalidDuplicateCandidateStateError):
            candidate.confirm()

    def test_dismiss_requires_reason(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        with pytest.raises(InvalidDuplicateCandidateStateError):
            candidate.dismiss("")

    def test_dismiss_from_detected_allowed(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        candidate.dismiss("no es duplicado")
        assert candidate.status.value == "DISMISSED"

    def test_mark_merged_requires_confirmed(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        with pytest.raises(InvalidDuplicateCandidateStateError):
            candidate.mark_merged()

    def test_involves(self):
        candidate = CustomerDuplicateCandidate.detect("cust-1", "cust-2", ("Mismo RFC",))
        assert candidate.involves("cust-1") and candidate.involves("cust-2")
        assert not candidate.involves("cust-3")


class TestCustomerMergeRecord:
    def test_propose_requires_distinct_customers(self):
        with pytest.raises(InvalidCustomerMergeStateError):
            CustomerMergeRecord.propose("cust-1", "cust-1", "u1")

    def test_propose_requires_proposer(self):
        with pytest.raises(InvalidCustomerMergeStateError):
            CustomerMergeRecord.propose("cust-1", "cust-2", "")

    def test_execute_transitions_to_executed(self):
        record = CustomerMergeRecord.propose("cust-1", "cust-2", "u1")
        record.execute("u2")
        assert record.status.value == "EXECUTED"
        assert record.executed_by_user_id == "u2"

    def test_execute_twice_raises(self):
        record = CustomerMergeRecord.propose("cust-1", "cust-2", "u1")
        record.execute("u2")
        with pytest.raises(InvalidCustomerMergeStateError):
            record.execute("u2")

    def test_reject_requires_reason(self):
        record = CustomerMergeRecord.propose("cust-1", "cust-2", "u1")
        with pytest.raises(InvalidCustomerMergeStateError):
            record.reject("u2", "")

    def test_reject_ok(self):
        record = CustomerMergeRecord.propose("cust-1", "cust-2", "u1")
        record.reject("u2", "no proceden a fusión")
        assert record.status.value == "REJECTED"

    def test_cannot_reject_after_execute(self):
        record = CustomerMergeRecord.propose("cust-1", "cust-2", "u1")
        record.execute("u2")
        with pytest.raises(InvalidCustomerMergeStateError):
            record.reject("u2", "motivo")


class TestCustomerDataQualityIssue:
    def test_detect_requires_customer_id(self):
        with pytest.raises(InvalidDataQualityIssueStateError):
            CustomerDataQualityIssue.detect("", DataQualityRuleCode.INCOMPLETE_NAME)

    def test_full_lifecycle_to_corrected(self):
        issue = CustomerDataQualityIssue.detect("cust-1", DataQualityRuleCode.INVALID_EMAIL)
        issue.acknowledge("u1")
        issue.correct()
        assert issue.status.value == "CORRECTED"
        assert issue.is_resolved()

    def test_correct_requires_acknowledged(self):
        issue = CustomerDataQualityIssue.detect("cust-1", DataQualityRuleCode.INVALID_EMAIL)
        with pytest.raises(InvalidDataQualityIssueStateError):
            issue.correct()

    def test_dismiss_requires_reason(self):
        issue = CustomerDataQualityIssue.detect("cust-1", DataQualityRuleCode.INVALID_EMAIL)
        with pytest.raises(InvalidDataQualityIssueStateError):
            issue.dismiss("u1", "")

    def test_dismiss_from_open_allowed(self):
        issue = CustomerDataQualityIssue.detect("cust-1", DataQualityRuleCode.INVALID_EMAIL)
        issue.dismiss("u1", "falso positivo")
        assert issue.status.value == "DISMISSED"
        assert issue.is_resolved()


class TestCustomerImportBatch:
    def test_start_requires_rows(self):
        with pytest.raises(InvalidCustomerImportError):
            CustomerImportBatch.start("u1", 0)

    def test_start_non_sensitive_goes_straight_to_processing(self):
        batch = CustomerImportBatch.start("u1", 5)
        assert batch.status is ImportBatchStatus.PROCESSING

    def test_start_sensitive_requires_approval(self):
        batch = CustomerImportBatch.start("u1", 5, is_sensitive=True)
        assert batch.status is ImportBatchStatus.PENDING_APPROVAL

    def test_approve_transitions_to_processing(self):
        batch = CustomerImportBatch.start("u1", 5, is_sensitive=True)
        batch.approve("u2")
        assert batch.status is ImportBatchStatus.PROCESSING
        assert batch.approved_by_user_id == "u2"

    def test_approve_non_sensitive_batch_raises(self):
        batch = CustomerImportBatch.start("u1", 5)
        with pytest.raises(InvalidCustomerImportError):
            batch.approve("u2")

    def test_reject_sensitive_batch(self):
        batch = CustomerImportBatch.start("u1", 5, is_sensitive=True)
        batch.reject()
        assert batch.status is ImportBatchStatus.REJECTED

    def test_finalize_all_success_is_completed(self):
        batch = CustomerImportBatch.start("u1", 2)
        batch.record_row("CREATED")
        batch.record_row("UPDATED")
        batch.finalize()
        assert batch.status is ImportBatchStatus.COMPLETED

    def test_finalize_mixed_is_partial(self):
        batch = CustomerImportBatch.start("u1", 2)
        batch.record_row("CREATED")
        batch.record_row("ERROR")
        batch.finalize()
        assert batch.status is ImportBatchStatus.PARTIAL

    def test_finalize_all_errors_is_failed(self):
        batch = CustomerImportBatch.start("u1", 2)
        batch.record_row("ERROR")
        batch.record_row("ERROR")
        batch.finalize()
        assert batch.status is ImportBatchStatus.FAILED

    def test_record_row_unknown_outcome_raises(self):
        batch = CustomerImportBatch.start("u1", 1)
        with pytest.raises(InvalidCustomerImportError):
            batch.record_row("WEIRD")


class TestCustomerDataQualityService:
    def _evaluate(self, **overrides):
        defaults = dict(display_name="Maria Lopez", phone_e164="+525512345678",
                        email="maria@example.com", tax_identifier="XAXX010101000",
                        has_address=True)
        defaults.update(overrides)
        return CustomerDataQualityService().evaluate(**defaults)

    def test_clean_customer_has_no_issues(self):
        assert self._evaluate() == []

    def test_incomplete_name_single_word(self):
        codes = [c for c, _ in self._evaluate(display_name="Maria")]
        assert DataQualityRuleCode.INCOMPLETE_NAME in codes

    def test_invalid_phone(self):
        codes = [c for c, _ in self._evaluate(phone_e164="555-1234")]
        assert DataQualityRuleCode.INVALID_PHONE in codes

    def test_missing_phone_is_not_flagged(self):
        """Absence isn't malformed-ness — only a present-but-invalid phone
        is a data-quality issue here, matching how PhoneNumber is optional
        elsewhere in this bounded context."""
        codes = [c for c, _ in self._evaluate(phone_e164=None)]
        assert DataQualityRuleCode.INVALID_PHONE not in codes

    def test_invalid_email(self):
        codes = [c for c, _ in self._evaluate(email="not-an-email")]
        assert DataQualityRuleCode.INVALID_EMAIL in codes

    def test_invalid_tax_id(self):
        codes = [c for c, _ in self._evaluate(tax_identifier="123")]
        assert DataQualityRuleCode.INVALID_TAX_ID in codes

    def test_incomplete_address(self):
        codes = [c for c, _ in self._evaluate(has_address=False)]
        assert DataQualityRuleCode.INCOMPLETE_ADDRESS in codes

    def test_multiple_violations_all_reported(self):
        codes = [c for c, _ in self._evaluate(
            display_name="Maria", phone_e164="bad", email="bad", tax_identifier="bad",
            has_address=False)]
        assert len(codes) == 5
