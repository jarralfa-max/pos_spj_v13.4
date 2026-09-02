"""OrderTotals — the canonical breakdown of a CustomerOrder's money (master
prompt §11, §27). This is the single source of truth for what an order is
worth; `CustomerOrder` itself embeds one `OrderTotals` instance rather than
four separate loose-Decimal fields, so subtotal/discount/delivery_fee/tax/
grand_total can never drift out of sync with each other — always produced by
`OrderTotalsService.calculate()`, never hand-assembled by a caller. Mirrors
`backend/domain/sales/value_objects/sale_totals.py` exactly, with
`delivery_fee` added (§11 lists it as its own field — Delivery doesn't
modify product prices, §22, but its fee is still part of what the customer
owes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.orders_delivery.exceptions import InvalidOrderMoneyError
from backend.domain.orders_delivery.value_objects.order_money import money


@dataclass(frozen=True, slots=True)
class OrderTotals:
    subtotal: Decimal
    discount_total: Decimal = Decimal("0")
    delivery_fee: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    rounding_adjustment: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "subtotal", money(self.subtotal))
        object.__setattr__(self, "discount_total", money(self.discount_total))
        object.__setattr__(self, "delivery_fee", money(self.delivery_fee))
        object.__setattr__(self, "tax_total", money(self.tax_total))
        object.__setattr__(self, "rounding_adjustment",
                            money(self.rounding_adjustment, allow_negative=True))
        object.__setattr__(self, "grand_total", money(self.grand_total, allow_negative=True))

        expected = (
            self.subtotal - self.discount_total + self.delivery_fee
            + self.tax_total + self.rounding_adjustment
        )
        if self.grand_total != expected:
            raise InvalidOrderMoneyError(
                f"OrderTotals.grand_total ({self.grand_total}) no coincide con la suma de "
                f"sus componentes ({expected}) — usar OrderTotalsService.calculate()"
            )

    @classmethod
    def zero(cls) -> "OrderTotals":
        return cls(subtotal=Decimal("0"), grand_total=Decimal("0"))
