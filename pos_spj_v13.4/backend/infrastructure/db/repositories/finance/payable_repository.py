"""Payable repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.payable import Payable
from backend.domain.finance.enums import PayableStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, supplier_id, financial_document_id, original_amount, outstanding_amount,"
            " currency_code, issue_date, due_date, branch_id, status, operation_id,"
            " created_at, updated_at")


def _to_entity(row: dict) -> Payable:
    currency = row["currency_code"]
    return Payable(
        id=row["id"], supplier_id=row["supplier_id"],
        financial_document_id=row["financial_document_id"],
        original_amount=Money.from_string(row["original_amount"], currency),
        outstanding_amount=Money.from_string(row["outstanding_amount"], currency),
        issue_date=date.fromisoformat(row["issue_date"]),
        operation_id=row["operation_id"],
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        branch_id=row["branch_id"],
        status=PayableStatus(row["status"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class PayableRepository(FinanceRepositoryBase):
    def save(self, payable: Payable) -> None:
        self._execute(
            f"INSERT INTO payables ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payable.id, payable.supplier_id, payable.financial_document_id,
             payable.original_amount.to_string(), payable.outstanding_amount.to_string(),
             payable.original_amount.currency_code, payable.issue_date.isoformat(),
             payable.due_date.isoformat() if payable.due_date else None,
             payable.branch_id, payable.status.value, payable.operation_id,
             payable.created_at, payable.updated_at),
        )

    def update(self, payable: Payable) -> None:
        self._execute(
            "UPDATE payables SET outstanding_amount=?, status=?, updated_at=? WHERE id=?",
            (payable.outstanding_amount.to_string(), payable.status.value,
             payable.updated_at, payable.id),
        )

    def get(self, payable_id: str) -> Payable | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM payables WHERE id=?", (payable_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Payable | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM payables WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None

    def list_open_by_supplier(self, supplier_id: str) -> list[Payable]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM payables WHERE supplier_id=?"
            " AND status IN ('OPEN','SCHEDULED','PARTIALLY_PAID') ORDER BY issue_date",
            (supplier_id,),
        )
        return [_to_entity(row) for row in rows]

    def list_open(self) -> list[Payable]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM payables"
            " WHERE status IN ('OPEN','SCHEDULED','PARTIALLY_PAID') ORDER BY issue_date"
        )
        return [_to_entity(row) for row in rows]
