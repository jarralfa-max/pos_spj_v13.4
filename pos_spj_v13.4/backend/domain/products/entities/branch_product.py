"""BranchProduct — the per-branch enablement of a product (§29).

A product is NOT duplicated per branch: there is one product and many
``BranchProduct`` rows deciding whether it is available at a given branch. This
entity carries NO operational price (price belongs to Pricing) and NO stock (stock
belongs to Inventory) — only availability + notes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidBranchProductError
from backend.shared.ids import new_uuid


@dataclass
class BranchProduct:
    product_id: str
    branch_id: str
    id: str = field(default_factory=new_uuid)
    enabled: bool = True
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidBranchProductError("La asignación requiere producto")
        if not self.branch_id:
            raise InvalidBranchProductError("La asignación requiere sucursal")
