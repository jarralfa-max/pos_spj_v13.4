"""PayableService — domain rules for accounts payable and supplier payments."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.payable import Payable, SupplierPayment
from backend.domain.finance.policies.payment_authorization_policy import PaymentAuthorizationPolicy
from backend.domain.finance.value_objects.money import Money


class PayableService:
    """Segregated lifecycle: obligation → schedule → authorize → execute → reconcile."""

    def __init__(self) -> None:
        self._auth_policy = PaymentAuthorizationPolicy()

    def create_obligation(
        self,
        supplier_id: str,
        financial_document_id: str,
        amount: Money,
        issue_date: date,
        operation_id: str,
        *,
        due_date: date | None = None,
        branch_id: str | None = None,
    ) -> Payable:
        return Payable.create(
            supplier_id=supplier_id,
            financial_document_id=financial_document_id,
            amount=amount,
            issue_date=issue_date,
            operation_id=operation_id,
            due_date=due_date,
            branch_id=branch_id,
        )

    def schedule_payment(
        self,
        payable: Payable,
        amount: Money,
        scheduled_date: date,
        treasury_account_id: str,
        operation_id: str,
        *,
        scheduled_by: str | None = None,
        reference: str = "",
    ) -> SupplierPayment:
        # Scheduling does not touch the payable balance; only execution does.
        return SupplierPayment.schedule(
            payable_id=payable.id,
            supplier_id=payable.supplier_id,
            amount=amount,
            scheduled_date=scheduled_date,
            treasury_account_id=treasury_account_id,
            operation_id=operation_id,
            scheduled_by=scheduled_by,
            reference=reference,
            branch_id=payable.branch_id,
        )

    def authorize_payment(self, payment: SupplierPayment, authorizer_id: str) -> None:
        self._auth_policy.enforce_authorization(payment, authorizer_id)
        payment.authorize(authorizer_id)

    def execute_payment(self, payment: SupplierPayment, payable: Payable,
                        executed_date: date, journal_entry_id: str) -> None:
        self._auth_policy.enforce_execution(payment, payable.outstanding_amount)
        payable.apply_payment(payment.amount)
        payment.execute(executed_date, journal_entry_id)
