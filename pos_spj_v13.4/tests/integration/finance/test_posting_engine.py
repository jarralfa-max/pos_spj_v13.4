"""FASES 3-5 — posting engine: idempotency, reversals, period control, atomicity."""

from datetime import date

import pytest

from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalEntryStatus, JournalType, PostingPurpose
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    PeriodClosedError,
    UnbalancedEntryError,
)
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.money import Money
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid

ENTRY_DATE = date(2026, 7, 16)


@pytest.fixture
def engine():
    return PostingEngine()


def _accounts(uow):
    return {
        "cash": uow.accounts.get_by_code("1102").id,
        "revenue": uow.accounts.get_by_code("4101").id,
        "tax": uow.accounts.get_by_code("2110").id,
    }


def _sale_lines(ids, total="116.00", revenue="100.00", tax="16.00"):
    return [
        LineSpec(ids["cash"], debit=Money.from_string(total)),
        LineSpec(ids["revenue"], credit=Money.from_string(revenue)),
        LineSpec(ids["tax"], credit=Money.from_string(tax)),
    ]


def _reference(doc_id=None, purpose=PostingPurpose.SALE_REVENUE, op=None):
    return PostingReference(
        source_module="sales", source_document_id=doc_id or new_uuid(),
        posting_purpose=purpose, operation_id=op or new_uuid(),
    )


class TestPosting:
    def test_posts_balanced_entry(self, bootstrapped_conn, engine):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                                _reference(), _sale_lines(_accounts(uow)))
        assert entry.status is JournalEntryStatus.POSTED
        assert entry.entry_number.startswith("SAL-")
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.journal_entries.get(entry.id)
        assert stored is not None and len(stored.lines) == 3
        assert stored.total_debits().to_string() == "116.00"

    def test_unbalanced_rejected(self, bootstrapped_conn, engine):
        with pytest.raises(UnbalancedEntryError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                ids = _accounts(uow)
                engine.post(uow, JournalType.SALES, ENTRY_DATE, "Mal",
                            _reference(), [
                                LineSpec(ids["cash"], debit=Money.from_string("100.00")),
                                LineSpec(ids["revenue"], credit=Money.from_string("99.00")),
                            ])

    def test_unknown_account_rejected(self, bootstrapped_conn, engine):
        with pytest.raises(FinanceDomainError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                engine.post(uow, JournalType.SALES, ENTRY_DATE, "Cuenta inexistente",
                            _reference(), [
                                LineSpec(new_uuid(), debit=Money.from_string("10.00")),
                                LineSpec(new_uuid(), credit=Money.from_string("10.00")),
                            ])

    def test_entry_numbers_are_sequential(self, bootstrapped_conn, engine):
        numbers = []
        for _ in range(3):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                entry = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                                    _reference(), _sale_lines(_accounts(uow)))
                numbers.append(entry.entry_number)
        assert numbers == ["SAL-000001", "SAL-000002", "SAL-000003"]

    def test_outbox_receives_posted_event(self, bootstrapped_conn, engine):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                        _reference(), _sale_lines(_accounts(uow)))
            pending = uow.outbox.list_pending()
        names = {row["event_name"] for row in pending}
        assert "JOURNAL_ENTRY_POSTED" in names


class TestIdempotency:
    def test_same_posting_reference_returns_original(self, bootstrapped_conn, engine):
        doc = new_uuid()
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            first = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                                _reference(doc_id=doc), _sale_lines(_accounts(uow)))
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            second = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta reintento",
                                 _reference(doc_id=doc), _sale_lines(_accounts(uow)))
        assert second.id == first.id
        count = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert count == 1

    def test_same_operation_id_returns_original(self, bootstrapped_conn, engine):
        op = new_uuid()
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            first = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                                _reference(op=op), _sale_lines(_accounts(uow)))
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            second = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Otra",
                                 _reference(op=op), _sale_lines(_accounts(uow)))
        assert second.id == first.id


class TestReversal:
    def _post_one(self, conn, engine):
        with FinanceUnitOfWork(conn) as uow:
            return engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                               _reference(), _sale_lines(_accounts(uow)))

    def test_reversal_creates_mirror_and_marks_original(self, bootstrapped_conn, engine):
        original = self._post_one(bootstrapped_conn, engine)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.journal_entries.get(original.id)
            reversal = engine.reverse(uow, stored, ENTRY_DATE, "devolución", new_uuid())
        assert reversal.total_debits().to_string() == "116.00"
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.journal_entries.get(original.id)
            assert stored.status is JournalEntryStatus.REVERSED
            assert stored.reversed_by_entry_id == reversal.id

    def test_double_reversal_is_idempotent(self, bootstrapped_conn, engine):
        original = self._post_one(bootstrapped_conn, engine)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.journal_entries.get(original.id)
            first = engine.reverse(uow, stored, ENTRY_DATE, "devolución", new_uuid())
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            stored = uow.journal_entries.get(original.id)
            second = engine.reverse(uow, stored, ENTRY_DATE, "devolución otra vez", new_uuid())
        assert second.id == first.id
        count = bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        assert count == 2  # original + one reversal only


class TestPeriodControl:
    def test_posting_into_closed_period_fails(self, bootstrapped_conn, engine):
        from backend.application.use_cases.finance.fiscal_period_use_cases import (
            CloseFiscalPeriodUseCase,
        )
        CloseFiscalPeriodUseCase().execute(
            bootstrapped_conn, 2026, 7, closed_by=new_uuid(), operation_id=new_uuid(),
        )
        with pytest.raises(PeriodClosedError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta tardía",
                            _reference(), _sale_lines(_accounts(uow)))

    def test_auto_opens_missing_period(self, bootstrapped_conn, engine):
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = engine.post(uow, JournalType.SALES, date(2026, 8, 1), "Venta agosto",
                                _reference(), _sale_lines(_accounts(uow)))
        assert entry.status is JournalEntryStatus.POSTED
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            assert uow.fiscal_periods.find_by_code(2026, 8) is not None

    def test_reopen_allows_posting_again(self, bootstrapped_conn, engine):
        from backend.application.use_cases.finance.fiscal_period_use_cases import (
            CloseFiscalPeriodUseCase,
            ReopenFiscalPeriodUseCase,
        )
        CloseFiscalPeriodUseCase().execute(
            bootstrapped_conn, 2026, 7, closed_by=new_uuid(), operation_id=new_uuid(),
        )
        ReopenFiscalPeriodUseCase().execute(
            bootstrapped_conn, 2026, 7, reason="ajuste auditado", operation_id=new_uuid(),
        )
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta",
                                _reference(), _sale_lines(_accounts(uow)))
        assert entry.status is JournalEntryStatus.POSTED


class TestAtomicity:
    def test_failed_posting_rolls_back_everything(self, bootstrapped_conn, engine):
        """Document + entry + outbox must be atomic: a failing entry rolls back
        the financial document saved in the same UoW."""
        from backend.domain.finance.entities.financial_document import FinancialDocument
        from backend.domain.finance.enums import FinancialDocumentType

        with pytest.raises(UnbalancedEntryError):
            with FinanceUnitOfWork(bootstrapped_conn) as uow:
                ids = _accounts(uow)
                document = FinancialDocument.create(
                    FinancialDocumentType.SALES_INVOICE, "F-001", ENTRY_DATE,
                    Money.from_string("116.00"), "sales", new_uuid(), new_uuid(),
                )
                uow.financial_documents.save(document)
                engine.post(uow, JournalType.SALES, ENTRY_DATE, "Venta rota",
                            _reference(), [
                                LineSpec(ids["cash"], debit=Money.from_string("116.00")),
                                LineSpec(ids["revenue"], credit=Money.from_string("100.00")),
                            ])
        docs = bootstrapped_conn.execute("SELECT COUNT(*) FROM financial_documents").fetchone()[0]
        entries = bootstrapped_conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        outbox = bootstrapped_conn.execute("SELECT COUNT(*) FROM finance_outbox").fetchone()[0]
        assert docs == 0 and entries == 0 and outbox == 0
