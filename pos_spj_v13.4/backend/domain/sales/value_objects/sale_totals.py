"""SaleTotals — the canonical breakdown of a Sale's money (master prompt
§27). This is the single source of truth for what a Sale is worth; Sale
itself embeds one `SaleTotals` instance rather than four separate
loose-Decimal fields, so subtotal/discount/tax/total can never drift out of
sync with each other — always produced by `SaleTotalsService.calculate()`,
never hand-assembled by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.sales.exceptions import InvalidMoneyValueError
from backend.domain.sales.value_objects.money import money


@dataclass(frozen=True, slots=True)
class SaleTotals:
    gross_subtotal: Decimal
    discount_total: Decimal = Decimal("0")
    promotion_total: Decimal = Decimal("0")
    coupon_total: Decimal = Decimal("0")
    loyalty_total: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    rounding_adjustment: Decimal = Decimal("0")
    total: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "gross_subtotal", money(self.gross_subtotal))
        object.__setattr__(self, "discount_total", money(self.discount_total))
        object.__setattr__(self, "promotion_total", money(self.promotion_total))
        object.__setattr__(self, "coupon_total", money(self.coupon_total))
        object.__setattr__(self, "loyalty_total", money(self.loyalty_total))
        object.__setattr__(self, "tax_total", money(self.tax_total))
        object.__setattr__(self, "rounding_adjustment",
                            money(self.rounding_adjustment, allow_negative=True))
        object.__setattr__(self, "total", money(self.total, allow_negative=True))

        expected = (
            self.gross_subtotal
            - self.discount_total
            - self.promotion_total
            - self.coupon_total
            - self.loyalty_total
            + self.tax_total
            + self.rounding_adjustment
        )
        if self.total != expected:
            raise InvalidMoneyValueError(
                f"SaleTotals.total ({self.total}) no coincide con la suma de sus "
                f"componentes ({expected}) — usar SaleTotalsService.calculate()"
            )

    @classmethod
    def zero(cls) -> "SaleTotals":
        return cls(gross_subtotal=Decimal("0"), total=Decimal("0"))
