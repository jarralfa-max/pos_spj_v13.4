"""SaleReturnPolicy — POS-16/§42-44 invariants for returning line items and
reversing a completed sale.

`Sale.cancel()`/`SaleCancellationPolicy` (SALES-3) already own PRE-payment
cancellation and explicitly forbid it once a sale is COMPLETED (§42: "un
paga sale must be reversed, not cancelled"). This policy is the other half
that phase deliberately deferred: what's allowed AFTER a sale has been
paid.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.sales.enums import SaleStatus
from backend.domain.sales.exceptions import (
    ReturnQuantityExceededError,
    SaleReturnNotAllowedError,
    SaleReversalNotAllowedError,
)

_RETURNABLE_STATUSES = frozenset({SaleStatus.COMPLETED, SaleStatus.RETURNED_PARTIALLY})


class SaleReturnPolicy:
    @staticmethod
    def ensure_can_return(status: SaleStatus) -> None:
        if status not in _RETURNABLE_STATUSES:
            raise SaleReturnNotAllowedError(
                f"No se puede devolver mercancía con la venta en estado {status.value}")

    @staticmethod
    def ensure_quantity_within_line(
        *, line_quantity: Decimal, already_returned: Decimal, requested: Decimal,
    ) -> None:
        if requested <= 0:
            raise ReturnQuantityExceededError("La cantidad a devolver debe ser mayor a cero")
        if already_returned + requested > line_quantity:
            available = line_quantity - already_returned
            raise ReturnQuantityExceededError(
                f"Cantidad a devolver ({requested}) excede lo disponible ({available})")

    @staticmethod
    def ensure_can_reverse(status: SaleStatus) -> None:
        if status is not SaleStatus.COMPLETED:
            raise SaleReversalNotAllowedError(
                f"No se puede reversar una venta en estado {status.value} — "
                "solo una venta COMPLETED puede reversarse")
