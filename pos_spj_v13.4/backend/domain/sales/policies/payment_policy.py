"""SalePaymentPolicy — POS-13/§30-36 invariants for recording payment and
completing a sale.

The transition table already built in `lifecycle_policies.py::
SaleLifecyclePolicy.TRANSITIONS` (SALES-3) already permits both
`CHECKOUT_PENDING -> COMPLETED` directly (single-method fast path) and
`CHECKOUT_PENDING -> PAYMENT_PENDING -> COMPLETED` (multi-line/mixed path) —
this policy does not duplicate that table, it only adds the two checks the
status transition alone can't express: "is this status allowed to accept a
NEW payment line" and "has enough been recorded to actually complete."
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.sales.enums import PaymentMethod, SaleStatus
from backend.domain.sales.exceptions import (
    PaymentExceedsBalanceError,
    SaleInvalidStateError,
    SalePaymentIncompleteError,
)

_PAYABLE_STATUSES = frozenset({SaleStatus.CHECKOUT_PENDING, SaleStatus.PAYMENT_PENDING})


class SalePaymentPolicy:
    @staticmethod
    def ensure_can_record_payment(status: SaleStatus) -> None:
        if status not in _PAYABLE_STATUSES:
            raise SaleInvalidStateError(
                f"No se puede registrar un pago con la venta en estado {status.value}")

    @staticmethod
    def ensure_fully_paid(*, total_paid: Decimal, sale_total: Decimal) -> None:
        if total_paid < sale_total:
            raise SalePaymentIncompleteError(
                f"Pago incompleto: recibido {total_paid}, requerido {sale_total}")

    @staticmethod
    def ensure_amount_allowed(*, method: PaymentMethod, amount: Decimal,
                              outstanding: Decimal) -> None:
        """Sólo el efectivo admite cambio (§32-33). Una tarjeta, transferencia,
        crédito o Mercado Pago por más de lo que falta dejaría un "cambio" que
        nadie entrega: el cobro lo descontaba del efectivo, que no existía."""
        if method is not PaymentMethod.CASH and Decimal(str(amount)) > max(
                outstanding, Decimal("0")):
            raise PaymentExceedsBalanceError(
                f"Un pago con {method.value} no puede superar lo que falta por cobrar "
                f"({max(outstanding, Decimal('0'))}); sólo el efectivo admite cambio.")


@dataclass(frozen=True)
class CashTender:
    """Resultado de entregar efectivo contra un importe (§32)."""

    accepted: bool
    change: Decimal
    shortfall: Decimal


class CashPaymentPolicy:
    """El cambio y el faltante del efectivo, en Decimal (§32). La pantalla de
    cobro sólo los presenta."""

    @staticmethod
    def evaluate(*, total: Decimal, received: Decimal) -> CashTender:
        total = Decimal(str(total))
        received = Decimal(str(received))
        if received >= total:
            return CashTender(True, received - total, Decimal("0"))
        return CashTender(False, Decimal("0"), total - received)

