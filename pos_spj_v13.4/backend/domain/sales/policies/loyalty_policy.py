"""LoyaltyPolicy — POS-14/§38-41: when a Sale may accept a loyalty-point
redemption. Broader than `SalePaymentPolicy`'s payable-states set — a
cashier may redeem points while still building the cart (ACTIVE), not only
once checkout has started, so the customer sees the reduced total before
paying."""

from __future__ import annotations

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SaleInvalidStateError

_REDEEMABLE_STATUSES = frozenset({
    SaleStatus.ACTIVE, SaleStatus.CHECKOUT_PENDING, SaleStatus.PAYMENT_PENDING,
})


class LoyaltyPolicy:
    @staticmethod
    def ensure_can_redeem(status: SaleStatus) -> None:
        if status not in _REDEEMABLE_STATUSES:
            raise SaleInvalidStateError(
                f"No se puede canjear fidelidad con la venta en estado {status.value}")
