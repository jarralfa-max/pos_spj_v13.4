"""PayableService — domain rules for accounts payable and supplier payments."""

from __future__ import annotations

from datetime import date

from backend.domain.finance.entities.payable import Payable, SupplierAdvance, SupplierPayment
from backend.domain.finance.enums import PayableStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.policies.payment_authorization_policy import PaymentAuthorizationPolicy
from backend.domain.finance.value_objects.money import Money


class PayableService:
    """Segregated lifecycle: obligation → schedule → authorize → execute → reconcile."""

    def __init__(self) -> None:
        self._auth_policy = PaymentAuthorizationPolicy()

    def create_obligation(self, supplier_id: str, financial_document_id: str, amount: Money,
                          issue_date: date, operation_id: str, **kwargs) -> Payable:
        return Payable.create(supplier_id, financial_document_id, amount, issue_date,
                              operation_id, **kwargs)

    def schedule_payment(self, payable: Payable, amount: Money, scheduled_date: date,
                         treasury_account_id: str, operation_id: str, *,
                         scheduled_by: str | None = None, reference: str = "",
                         second_authorization_required: bool = False) -> SupplierPayment:
        payable.assert_payable()
        if amount > payable.outstanding_amount:
            raise FinanceDomainError(
                f"Programar {amount.to_string()} excede el saldo de la CxP "
                f"({payable.outstanding_amount.to_string()})")
        payment = SupplierPayment.schedule(
            payable_id=payable.id, supplier_id=payable.supplier_id, amount=amount,
            scheduled_date=scheduled_date, treasury_account_id=treasury_account_id,
            operation_id=operation_id, scheduled_by=scheduled_by, reference=reference,
            branch_id=payable.branch_id,
            second_authorization_required=second_authorization_required)
        payable.mark_payment_stage(PayableStatus.SCHEDULED)
        return payment

    def authorize_payment(self, payment: SupplierPayment, payable: Payable,
                          authorizer_id: str) -> bool:
        self._auth_policy.enforce_authorization(payment, authorizer_id)
        fully = payment.authorize(authorizer_id)
        if fully:
            payable.mark_payment_stage(PayableStatus.AUTHORIZED)
        return fully

    def execute_payment(self, payment: SupplierPayment, payable: Payable,
                        executed_date: date, journal_entry_id: str, *,
                        executed_by: str | None = None, execution_reference: str | None = None,
                        discount_amount: Money | None = None) -> None:
        self._auth_policy.enforce_execution(payment, payable)
        settled = payment.amount.add(discount_amount) if discount_amount is not None \
            else payment.amount
        payable.apply_payment(settled, as_of=executed_date)
        payment.execute(executed_date, journal_entry_id, executed_by=executed_by,
                        execution_reference=execution_reference,
                        discount_amount=discount_amount)

    @staticmethod
    def apply_advance(advance: SupplierAdvance, payable: Payable, amount: Money,
                      on_date: date) -> None:
        if advance.supplier_id != payable.supplier_id:
            raise FinanceDomainError("El anticipo es de otro proveedor")
        payable.assert_payable()
        advance.apply(amount)
        payable.apply_payment(amount, as_of=on_date)
