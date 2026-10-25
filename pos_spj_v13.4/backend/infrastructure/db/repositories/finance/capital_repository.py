"""Capital transactions and loans repository (§17)."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.capital import CapitalTransaction, Loan
from backend.domain.finance.enums import CapitalMovementKind
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)


def _loan(row: dict) -> Loan:
    currency = row["currency_code"]
    return Loan(id=row["id"], lender_name=row["lender_name"],
                principal_amount=Money.from_string(row["principal_amount"], currency),
                outstanding_principal=Money.from_string(row["outstanding_principal"], currency),
                start_date=date.fromisoformat(row["start_date"]),
                liability_account_id=row["liability_account_id"],
                operation_id=row["operation_id"], maturity_date=parse_date(row["maturity_date"]),
                status=row["status"], created_by=row["created_by"],
                created_at=row["created_at"], updated_at=row["updated_at"])


def _transaction(row: dict) -> CapitalTransaction:
    currency = row["currency_code"]
    return CapitalTransaction(
        id=row["id"], kind=CapitalMovementKind(row["kind"]),
        amount=Money.from_string(row["amount"], currency),
        interest_amount=Money.from_string(row["interest_amount"], currency),
        transaction_date=date.fromisoformat(row["transaction_date"]),
        treasury_account_id=row["treasury_account_id"], operation_id=row["operation_id"],
        counterparty=row["counterparty"], loan_id=row["loan_id"],
        financial_document_id=row["financial_document_id"],
        journal_entry_id=row["journal_entry_id"], created_by=row["created_by"],
        branch_id=row["branch_id"], created_at=row["created_at"])


class CapitalRepository(FinanceRepositoryBase):
    def save_loan(self, loan: Loan) -> None:
        self._insert("loans", {
            "id": loan.id, "lender_name": loan.lender_name,
            "principal_amount": loan.principal_amount.to_string(),
            "outstanding_principal": loan.outstanding_principal.to_string(),
            "currency_code": loan.principal_amount.currency_code,
            "start_date": loan.start_date.isoformat(), "maturity_date": iso(loan.maturity_date),
            "status": loan.status, "liability_account_id": loan.liability_account_id,
            "created_by": loan.created_by, "operation_id": loan.operation_id,
            "created_at": loan.created_at, "updated_at": loan.updated_at})

    def update_loan(self, loan: Loan) -> None:
        self._update("loans", {"outstanding_principal": loan.outstanding_principal.to_string(),
                               "status": loan.status, "updated_at": loan.updated_at},
                     where="id=?", params=(loan.id,))

    def get_loan(self, loan_id: str) -> Loan | None:
        row = self._query_one("SELECT * FROM loans WHERE id=?", (loan_id,))
        return _loan(row) if row else None

    def find_loan_by_operation_id(self, operation_id: str) -> Loan | None:
        row = self._query_one("SELECT * FROM loans WHERE operation_id=?", (operation_id,))
        return _loan(row) if row else None

    def list_open_loans(self) -> list[Loan]:
        return [_loan(r) for r in
                self._query("SELECT * FROM loans WHERE status='OPEN' ORDER BY start_date")]

    def save_transaction(self, transaction: CapitalTransaction) -> None:
        self._insert("capital_transactions", {
            "id": transaction.id, "kind": transaction.kind.value,
            "amount": transaction.amount.to_string(),
            "interest_amount": transaction.interest_amount.to_string(),
            "currency_code": transaction.amount.currency_code,
            "transaction_date": transaction.transaction_date.isoformat(),
            "treasury_account_id": transaction.treasury_account_id,
            "counterparty": transaction.counterparty, "loan_id": transaction.loan_id,
            "financial_document_id": transaction.financial_document_id,
            "journal_entry_id": transaction.journal_entry_id,
            "created_by": transaction.created_by, "branch_id": transaction.branch_id,
            "operation_id": transaction.operation_id, "created_at": transaction.created_at})

    def find_transaction_by_operation_id(self, operation_id: str) -> CapitalTransaction | None:
        row = self._query_one("SELECT * FROM capital_transactions WHERE operation_id=?",
                              (operation_id,))
        return _transaction(row) if row else None
