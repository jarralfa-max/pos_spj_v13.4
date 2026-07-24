"""ProductCost — the canonical cost of a product (PRC-2).

Owns the average / last / standard cost of a product (optionally per branch), fed
by Purchasing/Production. Money-only. Costing is separate from Pricing: cost is an
input to the margin policy and to BI profitability, never a sale price.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.pricing.enums import CostMethod
from backend.domain.pricing.exceptions import InvalidCostError
from backend.domain.pricing.value_objects.money import Money
from backend.shared.ids import new_uuid


@dataclass
class ProductCost:
    product_id: str
    average_cost: Money
    id: str = field(default_factory=new_uuid)
    branch_id: str | None = None
    last_cost: Money | None = None
    standard_cost: Money | None = None
    cost_method: CostMethod = CostMethod.AVERAGE
    effective_from: str | None = None

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidCostError("El costo requiere producto")
        for name in ("average_cost", "last_cost", "standard_cost"):
            v = getattr(self, name)
            if v is not None and not isinstance(v, Money):
                raise InvalidCostError(f"{name} debe ser Money")
        if not isinstance(self.cost_method, CostMethod):
            self.cost_method = CostMethod(str(self.cost_method))

    def effective_cost(self) -> Money:
        if self.cost_method is CostMethod.LAST and self.last_cost is not None:
            return self.last_cost
        if self.cost_method is CostMethod.STANDARD and self.standard_cost is not None:
            return self.standard_cost
        return self.average_cost
