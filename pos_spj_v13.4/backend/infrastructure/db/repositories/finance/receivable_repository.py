"""Receivable repository (§11)."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import PaymentPromise, Receivable
from backend.domain.finance.enums import OPEN_RECEIVABLE_STATUSES, ReceivableStatus, sql_in
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)

_OPEN = sql_in(OPEN_RECEIVABLE_STATUSES)


def _to_entity(row: dict) -> Receivable:
    currency = row["currency_code"]
    return Receivable(
        id=row["id"], customer_id=row["customer_id"],
        financial_document_id=row["financial_document_id"],
        original_amount=Money.from_string(row["original_amount"], currency),
        outstanding_amount=Money.from_string(row["outstanding_amount"], currency),
        issue_date=date.fromisoformat(row["issue_date"]),
        operation_id=row["operation_id"],
        due_date=parse_date(row["due_date"]),
        branch_id=row["branch_id"],
        status=ReceivableStatus(row["status"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
        row_version=int(row["row_version"] or 0),
        credit_term_days=row["credit_term_days"],
        credit_origin=row["credit_origin"],
        dispute_reason=row["dispute_reason"], disputed_at=row["disputed_at"],
        disputed_by=row["disputed_by"], written_off_at=row["written_off_at"],
        written_off_by=row["written_off_by"], write_off_reason=row["write_off_reason"],
    )


def _mutable(receivable: Receivable) -> dict:
    return {
        "original_amount": receivable.original_amount.to_string(),
        "outstanding_amount": receivable.outstanding_amount.to_string(),
        "status": receivable.status.value,
        "dispute_reason": receivable.dispute_reason,
        "disputed_at": receivable.disputed_at,
        "disputed_by": receivable.disputed_by,
        "written_off_at": receivable.written_off_at,
        "written_off_by": receivable.written_off_by,
        "write_off_reason": receivable.write_off_reason,
        "updated_at": receivable.updated_at,
    }


class ReceivableRepository(FinanceRepositoryBase):
    def save(self, receivable: Receivable) -> None:
        values = {
            "id": receivable.id, "customer_id": receivable.customer_id,
            "financial_document_id": receivable.financial_document_id,
            "currency_code": receivable.original_amount.currency_code,
            "issue_date": receivable.issue_date.isoformat(),
            "due_date": iso(receivable.due_date),
            "credit_term_days": receivable.credit_term_days,
            "credit_origin": receivable.credit_origin,
            "branch_id": receivable.branch_id, "operation_id": receivable.operation_id,
            "row_version": receivable.row_version, "created_at": receivable.created_at,
        }
        values.update(_mutable(receivable))
        self._insert("receivables", values)

    def update(self, receivable: Receivable) -> None:
        values = _mutable(receivable)
        values["row_version"] = receivable.row_version + 1
        cursor = self._update("receivables", values, where="id=? AND row_version=?",
                              params=(receivable.id, receivable.row_version))
        if cursor.rowcount == 0:
            from backend.domain.finance.exceptions import ConcurrencyConflictError
            raise ConcurrencyConflictError(
                f"La cuenta por cobrar {receivable.id} cambió desde que se leyó; "
                "recargue y vuelva a intentar")
        receivable.row_version += 1

    def get(self, receivable_id: str) -> Receivable | None:
        row = self._query_one("SELECT * FROM receivables WHERE id=?", (receivable_id,))
        return _to_entity(row) if row else None

    def find_by_document(self, financial_document_id: str) -> Receivable | None:
        row = self._query_one("SELECT * FROM receivables WHERE financial_document_id=?",
                              (financial_document_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> Receivable | None:
        row = self._query_one("SELECT * FROM receivables WHERE operation_id=?", (operation_id,))
        return _to_entity(row) if row else None

    def list_open_by_customer(self, customer_id: str) -> list[Receivable]:
        rows = self._query(
            f"SELECT * FROM receivables WHERE customer_id=? AND status IN {_OPEN}"
            " ORDER BY COALESCE(due_date, issue_date), issue_date", (customer_id,))
        return [_to_entity(row) for row in rows]

    def list_open(self) -> list[Receivable]:
        rows = self._query(
            f"SELECT * FROM receivables WHERE status IN {_OPEN} ORDER BY issue_date")
        return [_to_entity(row) for row in rows]

    def list_overdue_candidates(self, as_of: date) -> list[Receivable]:
        rows = self._query(
            "SELECT * FROM receivables WHERE status IN ('OPEN','PARTIALLY_COLLECTED')"
            " AND due_date IS NOT NULL AND due_date < ?", (as_of.isoformat(),))
        return [_to_entity(row) for row in rows]

    # ── promesas de pago ─────────────────────────────────────────────────
    def save_promise(self, promise: PaymentPromise) -> None:
        self._insert("receivable_payment_promises", {
            "id": promise.id, "receivable_id": promise.receivable_id,
            "promised_date": promise.promised_date.isoformat(),
            "promised_amount": promise.promised_amount.to_string(),
            "currency_code": promise.promised_amount.currency_code, "note": promise.note,
            "status": promise.status, "created_by": promise.created_by,
            "operation_id": promise.operation_id, "created_at": promise.created_at,
            "updated_at": promise.updated_at,
        })

    def find_promise_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM receivable_payment_promises WHERE operation_id=?", (operation_id,))

    def get_promise(self, promise_id: str) -> PaymentPromise | None:
        row = self._query_one("SELECT * FROM receivable_payment_promises WHERE id=?",
                              (promise_id,))
        if row is None:
            return None
        return PaymentPromise(
            id=row["id"], receivable_id=row["receivable_id"],
            promised_date=date.fromisoformat(row["promised_date"]),
            promised_amount=Money.from_string(row["promised_amount"], row["currency_code"]),
            operation_id=row["operation_id"], note=row["note"], status=row["status"],
            created_by=row["created_by"], created_at=row["created_at"],
            updated_at=row["updated_at"])

    def update_promise(self, promise: PaymentPromise) -> None:
        self._update("receivable_payment_promises",
                     {"status": promise.status, "updated_at": promise.updated_at},
                     where="id=?", params=(promise.id,))

    def open_outstanding_total(self, currency_code: str):
        """Saldo vigente del auxiliar (Decimal)."""
        from decimal import Decimal
        total = Decimal("0")
        for row in self._query(
                f"SELECT outstanding_amount FROM receivables WHERE status IN {_OPEN}"
                " AND currency_code=?", (currency_code,)):
            total += Decimal(str(row["outstanding_amount"]))
        return total
