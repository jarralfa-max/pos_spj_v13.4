"""OrderTotalsService — the single place that computes a CustomerOrder's
`OrderTotals` (master prompt §9.3, §27). CustomerOrder never sums its own
lines inline; every mutation that changes money re-derives totals through
here, so subtotal/discount/delivery_fee/tax/grand_total can never be
computed two different ways in two different places.

This is the NEW canonical implementation `core/services/order_total_service.py`
(a self-declared compatibility shim over the legacy `DeliveryTotalService`,
see `docs/refactor/orders_delivery_legacy_inventory.md` §1) will eventually
be replaced by — not touched/deleted yet (ORD-29 legacy removal).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

from backend.domain.orders_delivery.value_objects.order_totals import OrderTotals

if TYPE_CHECKING:
    from backend.domain.orders_delivery.entities import CustomerOrderLine


class OrderTotalsService:
    @staticmethod
    def calculate(
        lines: Iterable["CustomerOrderLine"],
        *,
        order_level_discount: Decimal = Decimal("0"),
        delivery_fee: Decimal = Decimal("0"),
        rounding_adjustment: Decimal = Decimal("0"),
    ) -> OrderTotals:
        lines = list(lines)
        # ORD-10/§26-27: `final_subtotal` prices on the line's final
        # quantity/weight once catch-weight preparation/approval resolved
        # it, and gracefully falls back to the requested-equivalent amount
        # until then — so this is correct both before and after weighing,
        # never a separate "recalculate after adjustment" code path.
        subtotal = sum((line.final_subtotal for line in lines), Decimal("0"))
        line_discount_total = sum((line.discount_snapshot for line in lines), Decimal("0"))
        tax_total = sum((line.tax_snapshot for line in lines), Decimal("0"))
        discount_total = line_discount_total + order_level_discount

        grand_total = (
            subtotal - discount_total + delivery_fee + tax_total + rounding_adjustment
        )
        return OrderTotals(
            subtotal=subtotal,
            discount_total=discount_total,
            delivery_fee=delivery_fee,
            tax_total=tax_total,
            rounding_adjustment=rounding_adjustment,
            grand_total=grand_total,
        )
