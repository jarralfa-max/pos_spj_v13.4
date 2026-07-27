"""Receivable and Collection entities — accounts receivable domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import ReceivableStatus
from backend.domain.finance.exceptions import FinanceDomainError, InsufficientOutstandingError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Receivable:
    id: str
    customer_id: str
    financial_document_id: str
    original_amount: Money
    outstanding_amount: Money
    issue_date: date
    operation_id: str
    due_date: date | None = None
    branch_id: str | None = None
    status: ReceivableStatus = ReceivableStatus.OPEN
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, customer_id: str, financial_document_id: str, amount: Money,
               issue_date: date, operation_id: str, *,
               due_date: date | None = None, branch_id: str | None = None) -> "Receivable":
        if not customer_id:
            raise FinanceDomainError("Receivable requires a customer_id")
        if not amount.is_positive():
            raise FinanceDomainError("Receivable amount must be positive")
        return cls(
            id=new_uuid(), customer_id=customer_id,
            financial_document_id=financial_document_id,
            original_amount=amount, outstanding_amount=amount,
            issue_date=issue_date, operation_id=operation_id,
            due_date=due_date, branch_id=branch_id,
        )

    def apply_collection(self, amount: Money) -> None:
        if self.status in (ReceivableStatus.CANCELLED, ReceivableStatus.WRITTEN_OFF):
            raise FinanceDomainError(f"Cannot collect a {self.status.value} receivable")
        if not amount.is_positive():
            raise FinanceDomainError("Collection amount must be positive")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"Collection {amount.to_string()} exceeds outstanding {self.outstanding_amount.to_string()}"
            )
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        self.status = (ReceivableStatus.SETTLED if self.outstanding_amount.is_zero()
                       else ReceivableStatus.PARTIALLY_COLLECTED)
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status is ReceivableStatus.SETTLED:
            raise FinanceDomainError("A settled receivable cannot be cancelled; use a credit note")
        self.status = ReceivableStatus.CANCELLED
        self.outstanding_amount = Money.zero(self.original_amount.currency_code)
        self.updated_at = _utcnow()

    def days_overdue(self, as_of: date) -> int:
        if self.due_date is None or self.outstanding_amount.is_zero():
            return 0
        return max(0, (as_of - self.due_date).days)


@dataclass(slots=True)
class Collection:
    """A registered customer payment applied against one receivable."""

    id: str
    receivable_id: str
    customer_id: str
    amount: Money
    collection_date: date
    treasury_account_id: str
    operation_id: str
    journal_entry_id: str | None = None
    reference: str = ""
    branch_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, receivable_id: str, customer_id: str, amount: Money,
               collection_date: date, treasury_account_id: str, operation_id: str,
               *, reference: str = "", branch_id: str | None = None) -> "Collection":
        if not amount.is_positive():
            raise FinanceDomainError("Collection amount must be positive")
        if not treasury_account_id:
            raise FinanceDomainError("Collection requires a treasury_account_id")
        return cls(
            id=new_uuid(), receivable_id=receivable_id, customer_id=customer_id,
            amount=amount, collection_date=collection_date,
            treasury_account_id=treasury_account_id, operation_id=operation_id,
            reference=reference, branch_id=branch_id,
        )
