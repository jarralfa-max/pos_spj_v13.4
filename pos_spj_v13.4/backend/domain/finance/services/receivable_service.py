"""ReceivableService — domain rules for accounts receivable."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.receivable import Collection, Receivable
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.policies.credit_policy import CreditPolicy, CustomerCreditProfile
from backend.domain.finance.value_objects.money import Money


class ReceivableService:
    def __init__(self) -> None:
        self._credit_policy = CreditPolicy()

    def create_from_credit_sale(
        self,
        profile: CustomerCreditProfile | None,
        financial_document_id: str,
        sale_total: Money,
        issue_date: date,
        operation_id: str,
        *,
        due_date: date | None = None,
        branch_id: str | None = None,
    ) -> Receivable:
        self._credit_policy.enforce(profile, sale_total)
        assert profile is not None  # enforced above
        return Receivable.create(
            customer_id=profile.customer_id,
            financial_document_id=financial_document_id,
            amount=sale_total,
            issue_date=issue_date,
            operation_id=operation_id,
            due_date=due_date,
            branch_id=branch_id,
        )

    def register_collection(
        self,
        receivable: Receivable,
        amount: Money,
        collection_date: date,
        treasury_account_id: str,
        operation_id: str,
        *,
        reference: str = "",
        branch_id: str | None = None,
    ) -> Collection:
        """Apply a customer payment. The receivable enforces over-collection rules."""
        receivable.apply_collection(amount)
        return Collection.create(
            receivable_id=receivable.id,
            customer_id=receivable.customer_id,
            amount=amount,
            collection_date=collection_date,
            treasury_account_id=treasury_account_id,
            operation_id=operation_id,
            reference=reference,
            branch_id=branch_id or receivable.branch_id,
        )

    @staticmethod
    def aging_bucket(receivable: Receivable, as_of: date) -> str:
        days = receivable.days_overdue(as_of)
        if days == 0:
            return "CURRENT"
        if days <= 30:
            return "1-30"
        if days <= 60:
            return "31-60"
        if days <= 90:
            return "61-90"
        return "90+"

    @staticmethod
    def validate_customer_credit_note(amount: Money, receivable: Receivable) -> None:
        if amount > receivable.outstanding_amount:
            raise FinanceDomainError(
                "A credit note larger than the outstanding receivable creates a customer "
                "credit balance; route it through a STORE_CREDIT commercial obligation"
            )
