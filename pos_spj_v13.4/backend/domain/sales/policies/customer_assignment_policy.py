"""Customer assignment policy (master prompt §21). A customer can be
assigned or changed while the sale is still being built, but not once
checkout has produced a payment intent — the customer identity is part of
what the payment/credit/loyalty evaluation already committed to."""

from __future__ import annotations

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import SaleInvalidStateError

ASSIGNABLE_STATUSES = frozenset({
    SaleStatus.DRAFT, SaleStatus.ACTIVE, SaleStatus.SUSPENDED, SaleStatus.CHECKOUT_PENDING,
})


class CustomerAssignmentPolicy:
    @staticmethod
    def ensure_can_assign(status: SaleStatus) -> None:
        if status not in ASSIGNABLE_STATUSES:
            raise SaleInvalidStateError(
                f"No se puede asignar/cambiar cliente en una venta en estado {status}")
