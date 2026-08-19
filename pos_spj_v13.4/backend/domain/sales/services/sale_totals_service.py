"""SaleTotalsService — the single place that computes a Sale's `SaleTotals`
(master prompt §27, §8.2). Sale never sums its own lines inline; every
mutation that changes money re-derives totals through here, so
subtotal/discount/tax/total can never be computed two different ways in two
different places (the exact duplication master prompt §73 forbids: "Una sola
evaluación de precios").
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

from backend.domain.sales.value_objects.sale_totals import SaleTotals

if TYPE_CHECKING:
    from backend.domain.sales.entities import SaleLine


class SaleTotalsService:
    @staticmethod
    def calculate(
        lines: Iterable["SaleLine"],
        *,
        sale_level_discount: Decimal = Decimal("0"),
        promotion_total: Decimal = Decimal("0"),
        coupon_total: Decimal = Decimal("0"),
        loyalty_total: Decimal = Decimal("0"),
        rounding_adjustment: Decimal = Decimal("0"),
    ) -> SaleTotals:
        lines = list(lines)
        gross_subtotal = sum(
            (line.quantity.value * line.unit_price for line in lines), Decimal("0"))
        line_discount_total = sum((line.discount_total for line in lines), Decimal("0"))
        tax_total = sum((line.tax_total for line in lines), Decimal("0"))
        discount_total = line_discount_total + sale_level_discount

        total = (
            gross_subtotal - discount_total - promotion_total - coupon_total
            - loyalty_total + tax_total + rounding_adjustment
        )
        return SaleTotals(
            gross_subtotal=gross_subtotal,
            discount_total=discount_total,
            promotion_total=promotion_total,
            coupon_total=coupon_total,
            loyalty_total=loyalty_total,
            tax_total=tax_total,
            rounding_adjustment=rounding_adjustment,
            total=total,
        )
