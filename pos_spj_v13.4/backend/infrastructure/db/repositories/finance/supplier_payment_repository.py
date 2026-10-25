"""SupplierPayment and SupplierAdvance repository (§12)."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.payable import SupplierAdvance, SupplierPayment
from backend.domain.finance.enums import SupplierAdvanceStatus, SupplierPaymentStatus
from backend.domain.finance.value_objects.money import Money
from backend.infrastructure.db.repositories.finance.base import (
    FinanceRepositoryBase,
    iso,
    parse_date,
)


def _to_entity(row: dict) -> SupplierPayment:
    currency = row["currency_code"]
    return SupplierPayment(
        id=row["id"], payable_id=row["payable_id"], supplier_id=row["supplier_id"],
        amount=Money.from_string(row["amount"], currency),
        discount_amount=Money.from_string(row["discount_amount"] or "0", currency),
        scheduled_date=date.fromisoformat(row["scheduled_date"]),
        treasury_account_id=row["treasury_account_id"],
        operation_id=row["operation_id"],
        status=SupplierPaymentStatus(row["status"]),
        scheduled_by=row["scheduled_by"], authorized_by=row["authorized_by"],
        authorized_at=row["authorized_at"],
        second_authorization_required=bool(row["second_authorization_required"]),
        second_authorized_by=row["second_authorized_by"],
        second_authorized_at=row["second_authorized_at"],
        executed_at=row["executed_at"], executed_date=parse_date(row["executed_date"]),
        journal_entry_id=row["journal_entry_id"], reconciled_at=row["reconciled_at"],
        reference=row["reference"], branch_id=row["branch_id"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        executed_by=row["executed_by"], execution_reference=row["execution_reference"],
    )


def _mutable(payment: SupplierPayment) -> dict:
    return {
        "status": payment.status.value,
        "authorized_by": payment.authorized_by, "authorized_at": payment.authorized_at,
        "second_authorized_by": payment.second_authorized_by,
        "second_authorized_at": payment.second_authorized_at,
        "executed_by": payment.executed_by, "executed_at": payment.executed_at,
        "executed_date": iso(payment.executed_date),
        "execution_reference": payment.execution_reference,
        "discount_amount": payment.discount_amount.to_string(),
        "journal_entry_id": payment.journal_entry_id,
        "reconciled_at": payment.reconciled_at, "updated_at": payment.updated_at,
    }


def _advance_to_entity(row: dict) -> SupplierAdvance:
    currency = row["currency_code"]
    return SupplierAdvance(
        id=row["id"], supplier_id=row["supplier_id"],
        amount=Money.from_string(row["amount"], currency),
        applied_amount=Money.from_string(row["applied_amount"], currency),
        advance_date=date.fromisoformat(row["advance_date"]),
        treasury_account_id=row["treasury_account_id"], operation_id=row["operation_id"],
        status=SupplierAdvanceStatus(row["status"]), reference=row["reference"],
        branch_id=row["branch_id"], journal_entry_id=row["journal_entry_id"],
        created_by=row["created_by"], created_at=row["created_at"],
        updated_at=row["updated_at"])


class SupplierPaymentRepository(FinanceRepositoryBase):
    def save(self, payment: SupplierPayment) -> None:
        values = {
            "id": payment.id, "payable_id": payment.payable_id,
            "supplier_id": payment.supplier_id, "amount": payment.amount.to_string(),
            "currency_code": payment.amount.currency_code,
            "scheduled_date": payment.scheduled_date.isoformat(),
            "treasury_account_id": payment.treasury_account_id,
            "scheduled_by": payment.scheduled_by,
            "second_authorization_required": int(payment.second_authorization_required),
            "reference": payment.reference, "branch_id": payment.branch_id,
            "operation_id": payment.operation_id, "created_at": payment.created_at,
        }
        values.update(_mutable(payment))
        self._insert("supplier_payments", values)

    def update(self, payment: SupplierPayment) -> None:
        self._update("supplier_payments", _mutable(payment), where="id=?",
                     params=(payment.id,))

    def get(self, payment_id: str) -> SupplierPayment | None:
        row = self._query_one("SELECT * FROM supplier_payments WHERE id=?", (payment_id,))
        return _to_entity(row) if row else None

    def find_by_operation_id(self, operation_id: str) -> SupplierPayment | None:
        row = self._query_one("SELECT * FROM supplier_payments WHERE operation_id=?",
                              (operation_id,))
        return _to_entity(row) if row else None

    def list_by_payable(self, payable_id: str) -> list[SupplierPayment]:
        rows = self._query("SELECT * FROM supplier_payments WHERE payable_id=?"
                           " ORDER BY scheduled_date", (payable_id,))
        return [_to_entity(row) for row in rows]

    def list_pending_authorization(self) -> list[SupplierPayment]:
        rows = self._query("SELECT * FROM supplier_payments WHERE status='SCHEDULED'"
                           " ORDER BY scheduled_date")
        return [_to_entity(row) for row in rows]

    def in_flight_amount(self, payable_id: str) -> list[SupplierPayment]:
        rows = self._query("SELECT * FROM supplier_payments WHERE payable_id=?"
                           " AND status IN ('SCHEDULED','AUTHORIZED')", (payable_id,))
        return [_to_entity(row) for row in rows]

    # ── anticipos a proveedor ────────────────────────────────────────────
    def save_advance(self, advance: SupplierAdvance) -> None:
        self._insert("supplier_advances", {
            "id": advance.id, "supplier_id": advance.supplier_id,
            "branch_id": advance.branch_id, "treasury_account_id": advance.treasury_account_id,
            "amount": advance.amount.to_string(),
            "applied_amount": advance.applied_amount.to_string(),
            "currency_code": advance.amount.currency_code,
            "advance_date": advance.advance_date.isoformat(), "reference": advance.reference,
            "status": advance.status.value, "journal_entry_id": advance.journal_entry_id,
            "created_by": advance.created_by, "operation_id": advance.operation_id,
            "created_at": advance.created_at, "updated_at": advance.updated_at,
        })

    def update_advance(self, advance: SupplierAdvance) -> None:
        self._update("supplier_advances", {
            "applied_amount": advance.applied_amount.to_string(),
            "status": advance.status.value, "journal_entry_id": advance.journal_entry_id,
            "updated_at": advance.updated_at,
        }, where="id=?", params=(advance.id,))

    def get_advance(self, advance_id: str) -> SupplierAdvance | None:
        row = self._query_one("SELECT * FROM supplier_advances WHERE id=?", (advance_id,))
        return _advance_to_entity(row) if row else None

    def find_advance_by_operation_id(self, operation_id: str) -> SupplierAdvance | None:
        row = self._query_one("SELECT * FROM supplier_advances WHERE operation_id=?",
                              (operation_id,))
        return _advance_to_entity(row) if row else None

    def save_advance_application(self, *, application_id: str, advance_id: str,
                                 payable_id: str, amount: Money, journal_entry_id: str | None,
                                 created_by: str | None, operation_id: str,
                                 created_at: str) -> None:
        self._insert("supplier_advance_applications", {
            "id": application_id, "supplier_advance_id": advance_id, "payable_id": payable_id,
            "applied_amount": amount.to_string(), "currency_code": amount.currency_code,
            "journal_entry_id": journal_entry_id, "created_by": created_by,
            "operation_id": operation_id, "created_at": created_at,
        })

    def find_advance_application(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM supplier_advance_applications WHERE operation_id=?", (operation_id,))
