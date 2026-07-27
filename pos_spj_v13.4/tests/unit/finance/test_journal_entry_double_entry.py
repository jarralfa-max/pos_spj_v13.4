"""Double-entry invariants: balance, immutability, reversal-only corrections."""

import re
from datetime import date

import pytest

from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.enums import JournalEntryStatus, PostingPurpose
from backend.domain.finance.exceptions import (
    EmptyEntryError,
    ImmutableEntryError,
    PeriodClosedError,
    ReversalError,
    UnbalancedEntryError,
)
from backend.domain.finance.services.journal_posting_service import (
    JournalPostingService,
    LineSpec,
)
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.fixture
def service():
    return JournalPostingService()


@pytest.fixture
def period():
    return FiscalPeriod.open_for(2026, 7)


@pytest.fixture
def reference():
    return PostingReference(
        source_module="sales",
        source_document_id=new_uuid(),
        posting_purpose=PostingPurpose.SALE_REVENUE,
        operation_id=new_uuid(),
    )


def _build(service, period, reference, debit="100.00", credit="100.00"):
    return service.build_entry(
        journal_id=new_uuid(),
        entry_number="SAL-000001",
        entry_date=date(2026, 7, 15),
        fiscal_period=period,
        description="Venta de contado",
        posting_reference=reference,
        line_specs=[
            LineSpec(new_uuid(), debit=Money.from_string(debit)),
            LineSpec(new_uuid(), credit=Money.from_string(credit)),
        ],
    )


class TestDoubleEntryBalance:
    def test_balanced_entry_validates(self, service, period, reference):
        entry = _build(service, period, reference)
        assert entry.status is JournalEntryStatus.VALIDATED
        assert entry.total_debits().amount == entry.total_credits().amount

    def test_unbalanced_entry_rejected(self, service, period, reference):
        with pytest.raises(UnbalancedEntryError):
            _build(service, period, reference, debit="100.00", credit="99.99")

    def test_single_line_rejected(self, service, period, reference):
        with pytest.raises(EmptyEntryError):
            service.build_entry(
                journal_id=new_uuid(), entry_number="SAL-000002",
                entry_date=date(2026, 7, 15), fiscal_period=period,
                description="incompleto", posting_reference=reference,
                line_specs=[LineSpec(new_uuid(), debit=Money.from_string("50"))],
            )

    def test_line_with_both_sides_rejected(self, service, period, reference):
        from backend.domain.finance.entities.journal_entry import JournalLine
        line = JournalLine(
            id=new_uuid(), journal_entry_id=new_uuid(), account_id=new_uuid(),
            description="", debit=Money.from_string("10"), credit=Money.from_string("10"),
        )
        with pytest.raises(EmptyEntryError):
            line.validate()

    def test_uuidv7_identities(self, service, period, reference):
        entry = _build(service, period, reference)
        assert UUID_RE.match(entry.id)
        for line in entry.lines:
            assert UUID_RE.match(line.id)


class TestImmutability:
    def test_posted_entry_cannot_be_modified(self, service, period, reference):
        entry = _build(service, period, reference)
        service.post(entry, period)
        assert entry.status is JournalEntryStatus.POSTED
        with pytest.raises(ImmutableEntryError):
            entry.add_debit(new_uuid(), Money.from_string("1"))

    def test_posted_entry_cannot_be_cancelled(self, service, period, reference):
        entry = _build(service, period, reference)
        service.post(entry, period)
        with pytest.raises(ImmutableEntryError):
            entry.cancel()

    def test_posting_into_closed_period_rejected(self, service, period, reference):
        entry = _build(service, period, reference)
        period.close(closed_by=new_uuid())
        with pytest.raises(PeriodClosedError):
            service.post(entry, period)


class TestReversal:
    def _posted(self, service, period, reference):
        entry = _build(service, period, reference)
        service.post(entry, period)
        return entry

    def _reversal_ref(self):
        return PostingReference(
            source_module="sales", source_document_id=new_uuid(),
            posting_purpose=PostingPurpose.SALE_REVERSAL, operation_id=new_uuid(),
        )

    def test_reversal_mirrors_lines(self, service, period, reference):
        original = self._posted(service, period, reference)
        reversal = service.build_reversal(
            original, "SAL-000099", date(2026, 7, 16), period,
            "devolución total", self._reversal_ref(),
        )
        assert reversal.total_debits().amount == original.total_credits().amount
        assert reversal.total_credits().amount == original.total_debits().amount
        assert reversal.reversal_of_entry_id == original.id

    def test_post_reversal_marks_original_reversed(self, service, period, reference):
        original = self._posted(service, period, reference)
        reversal = service.build_reversal(
            original, "SAL-000099", date(2026, 7, 16), period,
            "devolución", self._reversal_ref(),
        )
        service.post_reversal(original, reversal, period)
        assert original.status is JournalEntryStatus.REVERSED
        assert original.reversed_by_entry_id == reversal.id
        assert reversal.status is JournalEntryStatus.POSTED

    def test_double_reversal_rejected(self, service, period, reference):
        original = self._posted(service, period, reference)
        reversal = service.build_reversal(
            original, "SAL-000099", date(2026, 7, 16), period,
            "devolución", self._reversal_ref(),
        )
        service.post_reversal(original, reversal, period)
        with pytest.raises(ReversalError):
            service.build_reversal(
                original, "SAL-000100", date(2026, 7, 17), period,
                "otra vez", self._reversal_ref(),
            )

    def test_draft_entry_cannot_be_reversed(self, service, period, reference):
        entry = _build(service, period, reference)  # VALIDATED, not POSTED
        with pytest.raises(ReversalError):
            service.build_reversal(
                entry, "SAL-000101", date(2026, 7, 16), period,
                "inválido", self._reversal_ref(),
            )

    def test_reversal_requires_reason(self, service, period, reference):
        original = self._posted(service, period, reference)
        with pytest.raises(ReversalError):
            service.build_reversal(
                original, "SAL-000102", date(2026, 7, 16), period,
                "   ", self._reversal_ref(),
            )
