"""Payment authorization policy — supplier payment control (§12, §28)."""

from __future__ import annotations

from backend.domain.finance.entities.payable import Payable, SupplierPayment
from backend.domain.finance.enums import SupplierPaymentStatus
from backend.domain.finance.exceptions import (
    PaymentAlreadyExecutedError,
    PaymentAuthorizationError,
    PaymentNotAuthorizedError,
)


class PaymentAuthorizationPolicy:
    def enforce_authorization(self, payment: SupplierPayment, authorizer_id: str) -> None:
        if payment.status is not SupplierPaymentStatus.SCHEDULED:
            raise PaymentAuthorizationError(
                f"El pago debe estar programado para autorizarse (está {payment.status.value})")
        if not authorizer_id or not authorizer_id.strip():
            raise PaymentAuthorizationError("La autorización requiere el usuario que autoriza")

    def enforce_execution(self, payment: SupplierPayment, payable: Payable) -> None:
        if payment.status in (SupplierPaymentStatus.EXECUTED, SupplierPaymentStatus.RECONCILED):
            raise PaymentAlreadyExecutedError("El pago ya se ejecutó; no se paga dos veces")
        if payment.status is not SupplierPaymentStatus.AUTHORIZED:
            raise PaymentNotAuthorizedError("Sólo se ejecuta un pago totalmente autorizado")
        payable.assert_payable()
        if payment.amount > payable.outstanding_amount:
            raise PaymentAuthorizationError(
                f"El pago de {payment.amount.to_string()} excede el saldo de la CxP "
                f"({payable.outstanding_amount.to_string()})")
