"""PricingResolutionService — the best-price rule (PRC-4).

Priority (from the legacy pricing_service): **volume > customer list > list > base**.
A global list discount applies to the list/customer/base price (a volume tier is an
explicit, already-discounted price). The minimum price is honoured: if the resolved
price falls below it, the result is flagged ``below_minimum`` (the use case then
requires a PRICING_PRICE_MIN_OVERRIDE hot authorization). Pure; Money/Decimal-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.pricing.enums import PriceSource
from backend.domain.pricing.value_objects.money import Money


@dataclass(frozen=True)
class PriceResolution:
    price: Money | None
    source: PriceSource
    min_price: Money | None = None
    below_minimum: bool = False


def _apply_discount(price: Money, discount_pct: Decimal) -> Money:
    if discount_pct <= 0:
        return price
    factor = Decimal("1") - (discount_pct / Decimal("100"))
    return price.multiply(factor)


class PricingResolutionService:
    def resolve(
        self,
        *,
        base_price: Money | None = None,
        list_price: Money | None = None,
        customer_price: Money | None = None,
        volume_price: Money | None = None,
        discount_pct: Decimal = Decimal("0"),
        min_price: Money | None = None,
    ) -> PriceResolution:
        # prioridad: volumen > lista cliente > lista > base
        if volume_price is not None:
            chosen, source = volume_price, PriceSource.VOLUME  # tier explícito, sin descuento
        elif customer_price is not None:
            chosen = _apply_discount(customer_price, discount_pct)
            source = PriceSource.CUSTOMER_LIST
        elif list_price is not None:
            chosen = _apply_discount(list_price, discount_pct)
            source = PriceSource.LIST
        elif base_price is not None:
            chosen = _apply_discount(base_price, discount_pct)
            source = PriceSource.BASE
        else:
            return PriceResolution(price=None, source=PriceSource.NONE, min_price=min_price)

        below = min_price is not None and chosen < min_price
        return PriceResolution(price=chosen, source=source, min_price=min_price,
                               below_minimum=below)
