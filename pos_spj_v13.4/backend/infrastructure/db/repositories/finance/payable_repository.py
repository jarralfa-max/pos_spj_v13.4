"""Payable repository (§12)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.finance.entities.payable import Payable
from backend.domain.finance.enums import (
    OPEN_PAYABLE_STATUSES,
    PayableStatus,
    PaymentPriority,
    PurchaseDebitNature,
    sql_in,
)
from backend.domain.finance.exceptions import ConcurrencyConflictError
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)

_OPEN = sql_in(OPEN_PAYABLE_STATUSES)


def _to_entity(row: dict) -> Payable:
    currency = row["currency_code"]
    discount = row["early_payment_discount_percent"]
    return Payable(
        id=row["id"], supplier_id=row["supplier_id"],
        financial_document_id=row["financial_document_id"],
        original_amount=Money.from_string(row["original_amount"], currency),
        outstanding_amount=Money.from_string(row["outstanding_amount"], currency),
        issue_date=date.fromisoformat(row["issue_date"]),
        operation_id=row["operation_id"],
        due_date=parse_date(row["due_date"]),
        branch_id=row["branch_id"],
        status=PayableStatus(row["status"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
        row_version=int(row["row_version"] or 0),
        priority=PaymentPriority(row["priority"]),
        payment_terms=row["payment_terms"] or "",
        debit_nature=PurchaseDebitNature(row["debit_nature"]),
        purchase_order_id=row["purchase_order_id"],
        goods_receipt_id=row["goods_receipt_id"],
        blocked=bool(row["blocked"]), block_reason=row["block_reason"],
        unblocked_by=row["unblocked_by"], unblock_reason=row["unblock_reason"],
        dispute_reason=row["dispute_reason"],
        retention_amount=Money.from_string(row["retention_amount"] or "0", currency),
        early_payment_discount_percent=Decimal(discount) if discount else None,
        early_payment_discount_until=parse_date(row["early_payment_discount_until"]),
    )


def _mutable(payable: Payable) -> dict:
    return {
        "outstanding_amount": payable.outstanding_amount.to_string(),
        "status": payable.status.value,
        "priority": payable.priority.value,
        "due_date": iso(payable.due_date),
        "blocked": int(payable.blocked),
        "block_reason": payable.block_reason,
        "unblocked_by": payable.unblocked_by,
        "unblock_reason": payable.unblock_reason,
        "dispute_reason": payable.dispute_reason,
        "updated_at": payable.updated_at,
    }


class PayableRepository(FinanceRepositoryBase):
    def save(self, payable: Payable) -> None:
        values = {
            "id": payable.id, "supplier_id": payable.supplier_id,
            "financial_document_id": payable.financial_document_id,
            "original_amount": payable.original_amount.to_string(),
            "currency_code": payable.original_amount.currency_code,
            "issue_date": payable.issue_date.isoformat(),
            "branch_id": payable.branch_id,
            "payment_terms": payable.payment_terms,
            "debit_nature": payable.debit_nature.value,
            "purchase_order_id": payable.purchase_order_id,
            "goods_receipt_id": payable.goods_receipt_id,
            "retention_amount": payable.retention_amount.to_string(),
            "early_payment_discount_percent": (format(payable.early_payment_discount_percent, "f")
                                               if payable.early_payment_discount_percent
                                               is not None else None),
            "early_payment_discount_until": iso(payable.early_payment_discount_until),
            "operation_id": payable.operation_id, "row_version": payable.row_version,
            "created_at": payable.created_at,
        }
        values.update(_mutable(payable))
        self._insert("payables", values)

    def update(self, payable: Payable) -> None:
        values = _mutable(payable)
        values["row_version"] = payable.row_version + 1
        cursor = self._update("payables", values, where="id=? AND row_version=?",
                              params=(payable.id, payable.row_version))
        if cursor.rowcount == 0:
            raise ConcurrencyConflictError(
                f"La cuenta por pagar {payable.id} cambió desde que se leyó; "
                "recargue y vuelva a intentar")
        payable.row_version += 1

    def get(self, payable_id: str) -> Payable | None:
        row = self._query_one("SELECT * FROM payables WHERE id=?", (payable_id,))
        return _to_entity(row) if row else None

    def find_by_document(self, financial_document_id: str) -> Payable | None:
        row = self._query_one("SELECT * FROM payables WHERE financial_document_id=?",
                              (financial_document_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Payable | None:
        row = self._query_one("SELECT * FROM payables WHERE operation_id=?", (operation_id,))
        return _to_entity(row) if row else None

    def find_by_goods_receipt(self, goods_receipt_id: str) -> list[Payable]:
        rows = self._query("SELECT * FROM payables WHERE goods_receipt_id=?",
                           (goods_receipt_id,))
        return [_to_entity(row) for row in rows]

    def list_open_by_supplier(self, supplier_id: str) -> list[Payable]:
        rows = self._query(
            f"SELECT * FROM payables WHERE supplier_id=? AND status IN {_OPEN}"
            " ORDER BY COALESCE(due_date, issue_date), issue_date", (supplier_id,))
        return [_to_entity(row) for row in rows]

    def list_open(self) -> list[Payable]:
        rows = self._query(f"SELECT * FROM payables WHERE status IN {_OPEN} ORDER BY issue_date")
        return [_to_entity(row) for row in rows]

    def list_overdue_candidates(self, as_of: date) -> list[Payable]:
        rows = self._query(
            "SELECT * FROM payables WHERE status IN ('OPEN','PARTIALLY_PAID')"
            " AND due_date IS NOT NULL AND due_date < ?", (as_of.isoformat(),))
        return [_to_entity(row) for row in rows]

    def open_outstanding_total(self, currency_code: str):
        """Saldo vigente del auxiliar (Decimal)."""
        from decimal import Decimal
        total = Decimal("0")
        for row in self._query(
                f"SELECT outstanding_amount FROM payables WHERE status IN {_OPEN}"
                " AND currency_code=?", (currency_code,)):
            total += Decimal(str(row["outstanding_amount"]))
        return total
