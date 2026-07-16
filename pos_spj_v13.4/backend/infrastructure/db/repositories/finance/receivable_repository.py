"""Receivable repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import Receivable
from backend.domain.finance.enums import ReceivableStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, customer_id, financial_document_id, original_amount, outstanding_amount,"
            " currency_code, issue_date, due_date, branch_id, status, operation_id,"
            " created_at, updated_at")


def _to_entity(row: dict) -> Receivable:
    currency = row["currency_code"]
    return Receivable(
        id=row["id"], customer_id=row["customer_id"],
        financial_document_id=row["financial_document_id"],
        original_amount=Money.from_string(row["original_amount"], currency),
        outstanding_amount=Money.from_string(row["outstanding_amount"], currency),
        issue_date=date.fromisoformat(row["issue_date"]),
        operation_id=row["operation_id"],
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        branch_id=row["branch_id"],
        status=ReceivableStatus(row["status"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class ReceivableRepository(FinanceRepositoryBase):
    def save(self, receivable: Receivable) -> None:
        self._execute(
            f"INSERT INTO receivables ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (receivable.id, receivable.customer_id, receivable.financial_document_id,
             receivable.original_amount.to_string(), receivable.outstanding_amount.to_string(),
             receivable.original_amount.currency_code, receivable.issue_date.isoformat(),
             receivable.due_date.isoformat() if receivable.due_date else None,
             receivable.branch_id, receivable.status.value, receivable.operation_id,
             receivable.created_at, receivable.updated_at),
        )

    def update(self, receivable: Receivable) -> None:
        self._execute(
            "UPDATE receivables SET outstanding_amount=?, status=?, updated_at=? WHERE id=?",
            (receivable.outstanding_amount.to_string(), receivable.status.value,
             receivable.updated_at, receivable.id),
        )

    def get(self, receivable_id: str) -> Receivable | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM receivables WHERE id=?", (receivable_id,))
        return _to_entity(row) if row else None

    def find_by_document(self, financial_document_id: str) -> Receivable | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM receivables WHERE financial_document_id=?",
            (financial_document_id,),
        )
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Receivable | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM receivables WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None

    def list_open_by_customer(self, customer_id: str) -> list[Receivable]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM receivables WHERE customer_id=?"
            " AND status IN ('OPEN','PARTIALLY_COLLECTED') ORDER BY issue_date",
            (customer_id,),
        )
        return [_to_entity(row) for row in rows]

    def list_open(self) -> list[Receivable]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM receivables"
            " WHERE status IN ('OPEN','PARTIALLY_COLLECTED') ORDER BY issue_date"
        )
        return [_to_entity(row) for row in rows]
