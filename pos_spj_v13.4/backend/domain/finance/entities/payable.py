"""Payable and SupplierPayment entities — accounts payable domain.

The payable lifecycle is explicitly segregated:
create obligation → schedule payment → authorize → execute → reconcile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import PayableStatus, SupplierPaymentStatus
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    InsufficientOutstandingError,
    PaymentAuthorizationError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Payable:
    id: str
    supplier_id: str
    financial_document_id: str
    original_amount: Money
    outstanding_amount: Money
    issue_date: date
    operation_id: str
    due_date: date | None = None
    branch_id: str | None = None
    status: PayableStatus = PayableStatus.OPEN
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, supplier_id: str, financial_document_id: str, amount: Money,
               issue_date: date, operation_id: str, *,
               due_date: date | None = None, branch_id: str | None = None) -> "Payable":
        if not supplier_id:
            raise FinanceDomainError("Payable requires a supplier_id")
        if not amount.is_positive():
            raise FinanceDomainError("Payable amount must be positive")
        return cls(
            id=new_uuid(), supplier_id=supplier_id,
            financial_document_id=financial_document_id,
            original_amount=amount, outstanding_amount=amount,
            issue_date=issue_date, operation_id=operation_id,
            due_date=due_date, branch_id=branch_id,
        )

    def apply_payment(self, amount: Money) -> None:
        if self.status is PayableStatus.CANCELLED:
            raise FinanceDomainError("Cannot pay a cancelled payable")
        if not amount.is_positive():
            raise FinanceDomainError("Payment amount must be positive")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"Payment {amount.to_string()} exceeds outstanding {self.outstanding_amount.to_string()}"
            )
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self.status = (PayableStatus.SETTLED if self.outstanding_amount.is_zero()
                       else PayableStatus.PARTIALLY_PAID)
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status is PayableStatus.SETTLED:
            raise FinanceDomainError("A settled payable cannot be cancelled; use a supplier credit note")
        self.status = PayableStatus.CANCELLED
        self.outstanding_amount = Money.zero(self.original_amount.currency_code)
        self.updated_at = _utcnow()


@dataclass(slots=True)
class SupplierPayment:
    """One supplier payment moving through schedule → authorize → execute → reconcile."""

    id: str
    payable_id: str
    supplier_id: str
    amount: Money
    scheduled_date: date
    treasury_account_id: str
    operation_id: str
    status: SupplierPaymentStatus = SupplierPaymentStatus.SCHEDULED
    scheduled_by: str | None = None
    authorized_by: str | None = None
    authorized_at: str | None = None
    executed_at: str | None = None
    executed_date: date | None = None
    journal_entry_id: str | None = None
    reconciled_at: str | None = None
    reference: str = ""
    branch_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def schedule(cls, payable_id: str, supplier_id: str, amount: Money,
                 scheduled_date: date, treasury_account_id: str, operation_id: str,
                 *, scheduled_by: str | None = None, reference: str = "",
                 branch_id: str | None = None) -> "SupplierPayment":
        if not amount.is_positive():
            raise FinanceDomainError("Scheduled payment amount must be positive")
        if not treasury_account_id:
            raise FinanceDomainError("Scheduled payment requires a treasury_account_id")
        return cls(
            id=new_uuid(), payable_id=payable_id, supplier_id=supplier_id,
            amount=amount, scheduled_date=scheduled_date,
            treasury_account_id=treasury_account_id, operation_id=operation_id,
            scheduled_by=scheduled_by, reference=reference, branch_id=branch_id,
        )

    def authorize(self, authorized_by: str) -> None:
        if self.status is not SupplierPaymentStatus.SCHEDULED:
            raise PaymentAuthorizationError(f"Cannot authorize payment in status {self.status.value}")
        if not authorized_by or not authorized_by.strip():
            raise PaymentAuthorizationError("Payment authorization requires the authorizing user id")
        if self.scheduled_by and authorized_by.strip() == self.scheduled_by:
            raise PaymentAuthorizationError(
                "Segregation of duties: the scheduler cannot authorize their own payment"
            )
        self.status = SupplierPaymentStatus.AUTHORIZED
        self.authorized_by = authorized_by.strip()
        self.authorized_at = _utcnow()
        self.updated_at = self.authorized_at

    def execute(self, executed_date: date, journal_entry_id: str) -> None:
        if self.status is not SupplierPaymentStatus.AUTHORIZED:
            raise PaymentAuthorizationError(
                f"Cannot execute payment in status {self.status.value}; authorization is mandatory"
            )
        self.status = SupplierPaymentStatus.EXECUTED
        self.executed_date = executed_date
        self.journal_entry_id = journal_entry_id
        self.executed_at = _utcnow()
        self.updated_at = self.executed_at

    def reconcile(self) -> None:
        if self.status is not SupplierPaymentStatus.EXECUTED:
            raise FinanceDomainError(f"Cannot reconcile payment in status {self.status.value}")
        self.status = SupplierPaymentStatus.RECONCILED
        self.reconciled_at = _utcnow()
        self.updated_at = self.reconciled_at

    def cancel(self) -> None:
        if self.status in (SupplierPaymentStatus.EXECUTED, SupplierPaymentStatus.RECONCILED):
            raise FinanceDomainError("An executed payment cannot be cancelled; register a reversal")
        self.status = SupplierPaymentStatus.CANCELLED
        self.updated_at = _utcnow()
