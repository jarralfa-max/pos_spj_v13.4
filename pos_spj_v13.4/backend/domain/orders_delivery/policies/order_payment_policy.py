"""OrderPaymentPolicy — CustomerOrder.payment_status invariants (master
prompt §15, §22). Same enum-transition-table shape as `OrderLifecyclePolicy`/
`SettlementPolicy`.

`payment_status` is a PROJECTION of the real money movement that happens in
the Sales bounded context (a `Sale`'s own payments/total_paid) — Orders/
Delivery never re-implements payment math, it only tracks which of the
eight §15 states currently applies. `resolve_from_amounts()` is the one
place that turns a paid amount into a status, mirroring the "one decision
function" pattern ORD-20/21 already used for cash-collection/settlement
outcomes.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.orders_delivery.enums import PaymentStatus
from backend.domain.orders_delivery.exceptions import InvalidPaymentStatusError


class OrderPaymentPolicy:
    FINAL_STATUSES = frozenset({PaymentStatus.REFUNDED})

    TRANSITIONS = {
        (PaymentStatus.UNPAID, PaymentStatus.AUTHORIZED),
        (PaymentStatus.UNPAID, PaymentStatus.PARTIALLY_PAID),
        (PaymentStatus.UNPAID, PaymentStatus.PAID),
        (PaymentStatus.UNPAID, PaymentStatus.PENDING_CASH_ON_DELIVERY),
        (PaymentStatus.UNPAID, PaymentStatus.CREDIT_APPROVED),
        (PaymentStatus.AUTHORIZED, PaymentStatus.PARTIALLY_PAID),
        (PaymentStatus.AUTHORIZED, PaymentStatus.PAID),
        (PaymentStatus.PARTIALLY_PAID, PaymentStatus.PARTIALLY_PAID),
        (PaymentStatus.PARTIALLY_PAID, PaymentStatus.PAID),
        (PaymentStatus.PARTIALLY_PAID, PaymentStatus.REFUND_PENDING),
        (PaymentStatus.PARTIALLY_PAID, PaymentStatus.REFUNDED),
        (PaymentStatus.PENDING_CASH_ON_DELIVERY, PaymentStatus.PARTIALLY_PAID),
        (PaymentStatus.PENDING_CASH_ON_DELIVERY, PaymentStatus.PAID),
        (PaymentStatus.CREDIT_APPROVED, PaymentStatus.PARTIALLY_PAID),
        (PaymentStatus.CREDIT_APPROVED, PaymentStatus.PAID),
        (PaymentStatus.PAID, PaymentStatus.REFUND_PENDING),
        (PaymentStatus.PAID, PaymentStatus.REFUNDED),
        (PaymentStatus.REFUND_PENDING, PaymentStatus.REFUNDED),
    }

    @classmethod
    def ensure_transition(cls, *, current: PaymentStatus, target: PaymentStatus) -> None:
        if current == target:
            return  # idempotent no-op — a repeated projection/webhook must not error
        if current in cls.FINAL_STATUSES:
            raise InvalidPaymentStatusError("Un pago ya reembolsado no puede transicionar")
        if (current, target) not in cls.TRANSITIONS:
            raise InvalidPaymentStatusError(
                f"Transición de pago inválida: {current.value} -> {target.value}")

    @staticmethod
    def resolve_from_amounts(*, total_paid: Decimal, order_total: Decimal) -> PaymentStatus:
        """Maps a Sale's actual paid amount onto one of the three
        amount-derived states. The other five states (AUTHORIZED,
        PENDING_CASH_ON_DELIVERY, CREDIT_APPROVED, REFUND_PENDING, REFUNDED)
        are set explicitly by their own use cases, never inferred here."""
        if total_paid <= Decimal("0"):
            return PaymentStatus.UNPAID
        if total_paid < order_total:
            return PaymentStatus.PARTIALLY_PAID
        return PaymentStatus.PAID
