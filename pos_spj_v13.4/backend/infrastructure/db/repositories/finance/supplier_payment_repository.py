"""SupplierPayment repository."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.payable import SupplierPayment
from backend.domain.finance.enums import SupplierPaymentStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, payable_id, supplier_id, amount, currency_code, scheduled_date,"
            " treasury_account_id, status, scheduled_by, authorized_by, authorized_at,"
            " executed_at, executed_date, journal_entry_id, reconciled_at, reference,"
            " branch_id, operation_id, created_at, updated_at")


def _to_entity(row: dict) -> SupplierPayment:
    return SupplierPayment(
        id=row["id"], payable_id=row["payable_id"], supplier_id=row["supplier_id"],
        amount=Money.from_string(row["amount"], row["currency_code"]),
        scheduled_date=date.fromisoformat(row["scheduled_date"]),
        treasury_account_id=row["treasury_account_id"],
        operation_id=row["operation_id"],
        status=SupplierPaymentStatus(row["status"]),
        scheduled_by=row["scheduled_by"], authorized_by=row["authorized_by"],
        authorized_at=row["authorized_at"], executed_at=row["executed_at"],
        executed_date=date.fromisoformat(row["executed_date"]) if row["executed_date"] else None,
        journal_entry_id=row["journal_entry_id"], reconciled_at=row["reconciled_at"],
        reference=row["reference"], branch_id=row["branch_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


class SupplierPaymentRepository(FinanceRepositoryBase):
    def save(self, payment: SupplierPayment) -> None:
        self._execute(
            f"INSERT INTO supplier_payments ({_COLUMNS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment.id, payment.payable_id, payment.supplier_id,
             payment.amount.to_string(), payment.amount.currency_code,
             payment.scheduled_date.isoformat(), payment.treasury_account_id,
             payment.status.value, payment.scheduled_by, payment.authorized_by,
             payment.authorized_at, payment.executed_at,
             payment.executed_date.isoformat() if payment.executed_date else None,
             payment.journal_entry_id, payment.reconciled_at, payment.reference,
             payment.branch_id, payment.operation_id, payment.created_at, payment.updated_at),
        )

    def update(self, payment: SupplierPayment) -> None:
        self._execute(
            "UPDATE supplier_payments SET status=?, authorized_by=?, authorized_at=?,"
            " executed_at=?, executed_date=?, journal_entry_id=?, reconciled_at=?, updated_at=?"
            " WHERE id=?",
            (payment.status.value, payment.authorized_by, payment.authorized_at,
             payment.executed_at,
             payment.executed_date.isoformat() if payment.executed_date else None,
             payment.journal_entry_id, payment.reconciled_at, payment.updated_at, payment.id),
        )

    def get(self, payment_id: str) -> SupplierPayment | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM supplier_payments WHERE id=?", (payment_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> SupplierPayment | None:
        row = self._query_one(
            f"SELECT {_COLUMNS} FROM supplier_payments WHERE operation_id=?", (operation_id,)
        )
        return _to_entity(row) if row else None

    def list_by_payable(self, payable_id: str) -> list[SupplierPayment]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM supplier_payments WHERE payable_id=? ORDER BY scheduled_date",
            (payable_id,),
        )
        return [_to_entity(row) for row in rows]

    def list_pending_authorization(self) -> list[SupplierPayment]:
        rows = self._query(
            f"SELECT {_COLUMNS} FROM supplier_payments WHERE status='SCHEDULED'"
            " ORDER BY scheduled_date"
        )
        return [_to_entity(row) for row in rows]
