"""AverageCostingService — moving weighted-average cost (PRC-6).

Pure domain rule: given the prior running (average, quantity) and an incoming
receipt (unit_cost, quantity), produce the new (average, quantity). Money/Decimal
only; the currency guard travels through ``Money``. Mirrors the legacy weighted
average (``cant_old*costo_old + qty*cost) / (cant_old + qty)``) with Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.pricing.exceptions import InvalidCostError
from backend.domain.pricing.value_objects.money import Money


@dataclass(frozen=True)
class CostUpdate:
    average_cost: Money
    tracked_quantity: Decimal
    last_cost: Money


class AverageCostingService:
    def apply_receipt(
        self,
        *,
        prior_average: Money | None,
        prior_quantity: Decimal,
        unit_cost: Money,
        incoming_quantity: Decimal,
    ) -> CostUpdate:
        if incoming_quantity <= 0:
            raise InvalidCostError("La cantidad recibida debe ser mayor a cero")
        if prior_quantity < 0:
            raise InvalidCostError("La cantidad previa no puede ser negativa")

        if prior_average is None or prior_quantity <= 0:
            new_qty = incoming_quantity
            return CostUpdate(average_cost=unit_cost, tracked_quantity=new_qty,
                              last_cost=unit_cost)

        # guard de moneda vía Money.multiply/add
        prior_value = prior_average.multiply(prior_quantity)
        incoming_value = unit_cost.multiply(incoming_quantity)
        new_qty = prior_quantity + incoming_quantity
        new_avg = prior_value.add(incoming_value).multiply(Decimal("1") / new_qty)
        return CostUpdate(average_cost=new_avg, tracked_quantity=new_qty,
                          last_cost=unit_cost)
