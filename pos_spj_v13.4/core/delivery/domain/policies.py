from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .states import AdjustmentStatus, DeliveryWorkflowType, normalize_workflow_type


@dataclass(frozen=True, slots=True)
class WeightAdjustmentDecision:
    requested_qty: float
    prepared_qty: float
    diff_qty: float
    diff_pct: float
    unit_price: float
    old_subtotal: float
    new_subtotal: float
    tolerance_units: float
    tolerance_exceeded: bool
    status: AdjustmentStatus
    apply_immediately: bool


class WeightAdjustmentPolicy:
    """Decides whether a prepared quantity can be applied automatically."""

    def __init__(self, tolerance_units: float = 0.2) -> None:
        if tolerance_units < 0:
            raise ValueError("La tolerancia de ajuste no puede ser negativa.")
        self.tolerance_units = float(tolerance_units)

    def evaluate(self, requested_qty: float, prepared_qty: float, unit_price: float) -> WeightAdjustmentDecision:
        requested = float(requested_qty or 0)
        prepared = float(prepared_qty or 0)
        price = float(unit_price or 0)
        if prepared < 0:
            raise ValueError("La cantidad preparada no puede ser negativa.")
        if requested < 0:
            raise ValueError("La cantidad solicitada no puede ser negativa.")
        if price < 0:
            raise ValueError("El precio unitario no puede ser negativo.")

        diff = round(prepared - requested, 6)
        diff_pct = round((abs(diff) / requested) * 100, 2) if requested else 0.0
        exceeded = requested > 0 and abs(diff) > self.tolerance_units
        return WeightAdjustmentDecision(
            requested_qty=requested,
            prepared_qty=prepared,
            diff_qty=diff,
            diff_pct=diff_pct,
            unit_price=price,
            old_subtotal=self._money(requested * price),
            new_subtotal=self._money(prepared * price),
            tolerance_units=self.tolerance_units,
            tolerance_exceeded=exceeded,
            status=AdjustmentStatus.PENDING_CUSTOMER if exceeded else AdjustmentStatus.AUTO_ACCEPTED,
            apply_immediately=not exceeded,
        )

    @staticmethod
    def _money(value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class DeliveryWorkflowPolicy:
    @staticmethod
    def requires_driver(workflow_type: str | DeliveryWorkflowType | None) -> bool:
        return normalize_workflow_type(workflow_type) == DeliveryWorkflowType.DELIVERY


class DeliveryTotalPolicy:
    @staticmethod
    def calculate_total(subtotals: Iterable[float]) -> float:
        total = sum(Decimal(str(s or 0)) for s in subtotals)
        return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
