"""FASE 8 — PURCHASE_RECEIVED: inventario contra CxP, nunca contra Caja."""

import pytest

from backend.application.event_handlers.finance.purchase_received_handler import (
    PurchaseReceivedHandler,
)
from backend.domain.finance.enums import PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
from backend.shared.ids import new_uuid


def _payload(**overrides):
    payload = {
        "event_id": new_uuid(), "operation_id": new_uuid(),
        "purchase_id": new_uuid(), "supplier_id": new_uuid(),
        "folio": "C-001", "occurred_at": "2026-07-16T09:00:00Z",
        "subtotal": "10000.00", "tax_total": "1600.00", "total": "11600.00",
    }
    payload.update(overrides)
    return payload


class TestPurchaseReceived:
    def test_creates_entry_document_and_payable(self, bootstrapped_conn):
        handler = PurchaseReceivedHandler(bootstrapped_conn)
        payload = _payload()
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            entry = uow.journal_entries.find_by_posting_reference(
                "purchases", payload["purchase_id"], PostingPurpose.PURCHASE_RECEIPT)
            payables = uow.payables.list_open_by_supplier(payload["supplier_id"])
        assert entry.is_balanced()
        assert entry.total_credits().to_string() == "11600.00"
        assert len(payables) == 1
        assert payables[0].outstanding_amount.to_string() == "11600.00"

    def test_purchase_never_touches_cash_register_account(self, bootstrapped_conn):
        """El asiento de compra no debe tocar la cuenta de Caja POS (1102)."""
        handler = PurchaseReceivedHandler(bootstrapped_conn)
        payload = _payload()
        handler.handle(payload)
        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            pos_account = uow.accounts.get_by_code("1102")
            entry = uow.journal_entries.find_by_posting_reference(
                "purchases", payload["purchase_id"], PostingPurpose.PURCHASE_RECEIPT)
        assert all(line.account_id != pos_account.id for line in entry.lines)

    def test_totals_must_reconcile(self, bootstrapped_conn):
        handler = PurchaseReceivedHandler(bootstrapped_conn)
        with pytest.raises(FinanceDomainError):
            handler.handle(_payload(total="99999.00"))

    def test_idempotent_by_event_and_by_purchase(self, bootstrapped_conn):
        handler = PurchaseReceivedHandler(bootstrapped_conn)
        payload = _payload()
        handler.handle(payload)
        handler.handle(payload)
        handler.handle(_payload(purchase_id=payload["purchase_id"],
                                supplier_id=payload["supplier_id"]))
        entries = bootstrapped_conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE posting_purpose='PURCHASE_RECEIPT'"
        ).fetchone()[0]
        payables = bootstrapped_conn.execute("SELECT COUNT(*) FROM payables").fetchone()[0]
        assert entries == 1 and payables == 1


class TestPeriodCloseChecklist:
    def test_open_reconciliation_blocks_close(self, bootstrapped_conn):
        from backend.application.use_cases.finance.fiscal_period_use_cases import (
            CloseFiscalPeriodUseCase,
        )
        from backend.application.use_cases.finance.reconcile_bank_statement_use_case import (
            ReconcileBankStatementUseCase,
        )
        from backend.application.use_cases.finance.treasury_use_cases import (
            ImportBankStatementUseCase,
        )
        from backend.domain.finance.enums import TreasuryAccountType
        from backend.domain.finance.exceptions import MaterialDifferenceError

        with FinanceUnitOfWork(bootstrapped_conn) as uow:
            bank = next(a for a in uow.treasury.list_active()
                        if a.account_type is TreasuryAccountType.BANK)
        statement = ImportBankStatementUseCase().execute(
            bootstrapped_conn, treasury_account_id=bank.id,
            statement_date=__import__("datetime").date(2026, 7, 16),
            opening_balance="0.00", closing_balance="0.00", lines=[],
            operation_id=new_uuid())
        ReconcileBankStatementUseCase().start(
            bootstrapped_conn, bank_statement_id=statement.id, operation_id=new_uuid())
        with pytest.raises(MaterialDifferenceError):
            CloseFiscalPeriodUseCase().execute(
                bootstrapped_conn, 2026, 7, closed_by=new_uuid(), operation_id=new_uuid())
