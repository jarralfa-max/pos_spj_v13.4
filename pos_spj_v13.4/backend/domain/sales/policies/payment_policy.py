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

from decimal import Decimal

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SaleInvalidStateError, SalePaymentIncompleteError

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
