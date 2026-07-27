"""FinancialDocument entity — the canonical source document of an economic fact."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import FinancialDocumentStatus, FinancialDocumentType
from backend.domain.finance.exceptions import FinanceDomainError, InsufficientOutstandingError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FinancialDocument:
    id: str
    document_type: FinancialDocumentType
    document_number: str
    issue_date: date
    total_amount: Money
    outstanding_amount: Money
    source_module: str
    source_document_id: str
    operation_id: str
    due_date: date | None = None
    exchange_rate: Decimal = Decimal("1")
    subtotal: Money | None = None
    tax_amount: Money | None = None
    discount_amount: Money | None = None
    status: FinancialDocumentStatus = FinancialDocumentStatus.OPEN
    branch_id: str | None = None
    customer_id: str | None = None
    supplier_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        document_type: FinancialDocumentType,
        document_number: str,
        issue_date: date,
        total_amount: Money,
        source_module: str,
        source_document_id: str,
        operation_id: str,
        **kwargs,
    ) -> "FinancialDocument":
        if total_amount.is_negative():
            raise FinanceDomainError("FinancialDocument.total_amount must not be negative")
        if not source_module or not source_document_id or not operation_id:
            raise FinanceDomainError("FinancialDocument requires source_module, source_document_id and operation_id")
        return cls(
            id=new_uuid(),
            document_type=document_type,
            document_number=document_number,
            issue_date=issue_date,
            total_amount=total_amount,
            outstanding_amount=total_amount,
            source_module=source_module,
            source_document_id=source_document_id,
            operation_id=operation_id,
            **kwargs,
        )

    @property
    def currency_code(self) -> str:
        return self.total_amount.currency_code

    def apply_settlement(self, amount: Money) -> None:
        """Reduce the outstanding amount; never below zero."""
        if not amount.is_positive():
            raise FinanceDomainError("Settlement amount must be positive")
        if amount > self.outstanding_amount:
            raise InsufficientOutstandingError(
                f"Settlement {amount.to_string()} exceeds outstanding "
                f"{self.outstanding_amount.to_string()} of document {self.document_number}"
            )
        self.outstanding_amount = self.outstanding_amount.subtract(amount)
        if self.outstanding_amount.is_zero():
            self.status = FinancialDocumentStatus.SETTLED
        else:
            self.status = FinancialDocumentStatus.PARTIALLY_SETTLED
        self.updated_at = _utcnow()

    def cancel(self) -> None:
        if self.status is FinancialDocumentStatus.SETTLED:
            raise FinanceDomainError("A settled document cannot be cancelled; issue a reversal document")
        self.status = FinancialDocumentStatus.CANCELLED
        self.updated_at = _utcnow()
