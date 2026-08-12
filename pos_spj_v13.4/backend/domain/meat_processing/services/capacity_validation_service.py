"""CapacityValidationService (§33). "La primera versión puede manejar
capacidad básica configurable sin construir un APS completo" — this sums a
set of ProductionPlanLine against a caller-supplied capacity limit; it does
not model work centers, shifts or equipment (PROC-19). The limit is always an
argument, never a hardcoded constant (root CLAUDE.md #23/24).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Literal

from backend.domain.meat_processing.entities.production_plan_line import ProductionPlanLine
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError

CapacityBasis = Literal["quantity", "weight"]


@dataclass(frozen=True)
class CapacityCheckResult:
    basis: CapacityBasis
    planned_load: Decimal
    capacity_limit: Decimal

    @property
    def within_capacity(self) -> bool:
        return self.planned_load <= self.capacity_limit

    @property
    def overage(self) -> Decimal:
        return max(Decimal("0"), self.planned_load - self.capacity_limit)

    @property
    def utilization_pct(self) -> Decimal | None:
        if self.capacity_limit == 0:
            return None
        return (self.planned_load / self.capacity_limit) * Decimal("100")


class CapacityValidationService:
    @staticmethod
    def validate(
        lines: Iterable[ProductionPlanLine],
        *,
        capacity_limit: Decimal,
        basis: CapacityBasis = "weight",
    ) -> CapacityCheckResult:
        if capacity_limit < 0:
            raise MeatProcessingInvariantError("capacity_limit no puede ser negativo")
        if basis not in ("quantity", "weight"):
            raise MeatProcessingInvariantError("basis debe ser 'quantity' o 'weight'")
        attribute = "planned_quantity" if basis == "quantity" else "planned_weight"
        planned_load = sum(
            (getattr(line, attribute) for line in lines), start=Decimal("0"))
        return CapacityCheckResult(
            basis=basis, planned_load=planned_load, capacity_limit=capacity_limit)
