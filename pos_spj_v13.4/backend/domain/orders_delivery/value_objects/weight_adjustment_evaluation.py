"""WeightAdjustmentEvaluation (master prompt §26) — the outcome of comparing
a line's prepared amount against what was requested. Pure value object;
`CatchWeightAdjustmentPolicy` is what produces one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.orders_delivery.value_objects.order_money import money


@dataclass(frozen=True, slots=True)
class WeightAdjustmentEvaluation:
    requested_amount: Decimal
    prepared_amount: Decimal
    unit_price: Decimal
    tolerance_pct: Decimal
    difference: Decimal
    difference_pct: Decimal
    within_tolerance: bool
    old_subtotal: Decimal
    proposed_subtotal: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "old_subtotal", money(self.old_subtotal))
        object.__setattr__(self, "proposed_subtotal", money(self.proposed_subtotal))
