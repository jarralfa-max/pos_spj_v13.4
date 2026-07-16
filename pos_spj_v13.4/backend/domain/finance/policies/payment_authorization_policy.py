"""Payment authorization policy — segregation of duties for supplier payments."""

from __future__ import annotations

from backend.domain.finance.entities.payable import SupplierPayment
from backend.domain.finance.enums import SupplierPaymentStatus
from backend.domain.finance.exceptions import PaymentAuthorizationError
from backend.domain.finance.value_objects.money import Money


class PaymentAuthorizationPolicy:
    def enforce_authorization(self, payment: SupplierPayment, authorizer_id: str) -> None:
        if payment.status is not SupplierPaymentStatus.SCHEDULED:
            raise PaymentAuthorizationError(
                f"Payment must be SCHEDULED to authorize (is {payment.status.value})"
            )
        if not authorizer_id or not authorizer_id.strip():
            raise PaymentAuthorizationError("Authorization requires the authorizing user id")
        if payment.scheduled_by and authorizer_id.strip() == payment.scheduled_by:
            raise PaymentAuthorizationError(
                "Segregation of duties: the scheduler cannot authorize their own payment"
            )

    def enforce_execution(self, payment: SupplierPayment, payable_outstanding: Money) -> None:
        if payment.status is not SupplierPaymentStatus.AUTHORIZED:
            raise PaymentAuthorizationError(
                f"Payment must be AUTHORIZED before execution (is {payment.status.value})"
            )
        if payment.amount > payable_outstanding:
            raise PaymentAuthorizationError(
                f"Payment {payment.amount.to_string()} exceeds payable outstanding "
                f"{payable_outstanding.to_string()}"
            )
