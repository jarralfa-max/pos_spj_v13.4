"""CatchWeightAdjustmentPolicy (master prompt §26-27). Compares a line's
prepared amount (weight if catch-weight, otherwise quantity) against what was
requested and decides whether it's within tolerance — the ONLY place this
comparison happens, so a line is never auto-accepted by one code path and
flagged by another. `tolerance_pct` is always supplied by the caller
(a configuration value, never hardcoded here — master prompt §22).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.orders_delivery.exceptions import InvalidOrderQuantityError
from backend.domain.orders_delivery.value_objects.weight_adjustment_evaluation import (
    WeightAdjustmentEvaluation,
)


class CatchWeightAdjustmentPolicy:
    @staticmethod
    def evaluate(
        *, requested_amount: Decimal, prepared_amount: Decimal, unit_price: Decimal,
        tolerance_pct: Decimal,
    ) -> WeightAdjustmentEvaluation:
        if tolerance_pct < 0:
            raise InvalidOrderQuantityError("La tolerancia no puede ser negativa")
        difference = prepared_amount - requested_amount
        if requested_amount == 0:
            difference_pct = Decimal("100") if difference != 0 else Decimal("0")
        else:
            difference_pct = (abs(difference) / requested_amount) * Decimal("100")
        within_tolerance = difference_pct <= tolerance_pct
        old_subtotal = requested_amount * unit_price
        proposed_subtotal = prepared_amount * unit_price
        return WeightAdjustmentEvaluation(
            requested_amount=requested_amount, prepared_amount=prepared_amount,
            unit_price=unit_price, tolerance_pct=tolerance_pct, difference=difference,
            difference_pct=difference_pct, within_tolerance=within_tolerance,
            old_subtotal=old_subtotal, proposed_subtotal=proposed_subtotal,
        )
