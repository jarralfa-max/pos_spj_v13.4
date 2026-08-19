"""Discount validation (master prompt §25-26). Pure domain decision: given a
proposed discount and the base it applies to, decide whether it is within
the unauthorized threshold or requires a hot authorization. Actually
granting/validating that authorization is `SalesAuthorizationPolicy`
(application layer, SALES-2) — this policy only decides IF one is required
and enforces that the caller already obtained it (`authorized=True`).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.sales.exceptions import DiscountNotAllowedError
from backend.domain.sales.value_objects.money import money

DEFAULT_MAX_UNAUTHORIZED_DISCOUNT_PERCENT = Decimal("20")


class SaleDiscountPolicy:
    @staticmethod
    def requires_authorization(
        *, discount_amount: Decimal, base_amount: Decimal,
        max_unauthorized_percent: Decimal = DEFAULT_MAX_UNAUTHORIZED_DISCOUNT_PERCENT,
    ) -> bool:
        discount_amount = money(discount_amount, allow_zero=True)
        base_amount = money(base_amount, allow_zero=True)
        if base_amount == 0:
            return discount_amount > 0
        percent = (discount_amount / base_amount) * Decimal("100")
        return percent > max_unauthorized_percent

    @classmethod
    def ensure_valid_discount(
        cls, *, discount_amount: Decimal, base_amount: Decimal, authorized: bool,
        max_unauthorized_percent: Decimal = DEFAULT_MAX_UNAUTHORIZED_DISCOUNT_PERCENT,
    ) -> None:
        discount_amount = money(discount_amount, allow_zero=True)
        base_amount = money(base_amount, allow_zero=True)
        if discount_amount > base_amount:
            raise DiscountNotAllowedError("El descuento no puede exceder el importe base")
        if not authorized and cls.requires_authorization(
            discount_amount=discount_amount, base_amount=base_amount,
            max_unauthorized_percent=max_unauthorized_percent,
        ):
            raise DiscountNotAllowedError(
                f"Descuento superior a {max_unauthorized_percent}% requiere autorización")
