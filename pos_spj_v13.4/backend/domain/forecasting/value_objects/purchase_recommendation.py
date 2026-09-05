"""PurchaseRecommendation (§29, BI-14).

BI observes and recommends; it never creates a PurchaseOrder (§29: "BI
recomienda. Compras ejecuta." / §34). This value object is the entire
output surface — there is no `execute()`/`create_purchase_order()` method
anywhere near it, deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class PurchaseRecommendation:
    id: str
    product_id: str
    branch_id: str
    suggested_quantity: Decimal
    coverage_days: Decimal
    expected_demand: Decimal
    current_stock: Decimal
    incoming_stock: Decimal
    safety_stock: Decimal
    supplier_lead_time_days: int
    estimated_cost: Decimal | None
    priority: RecommendationPriority
    confidence: Decimal
    created_at: datetime
    valid_until: date

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.product_id or not self.branch_id:
            raise ValueError("PurchaseRecommendation requires product_id and branch_id")
        for name in ("suggested_quantity", "expected_demand", "current_stock",
                     "incoming_stock", "safety_stock", "coverage_days"):
            if getattr(self, name) < 0:
                raise ValueError(f"PurchaseRecommendation.{name} must be >= 0")
        if self.supplier_lead_time_days < 0:
            raise ValueError("PurchaseRecommendation.supplier_lead_time_days must be >= 0")
        if self.estimated_cost is not None and self.estimated_cost < 0:
            raise ValueError("PurchaseRecommendation.estimated_cost must be >= 0 or None")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("PurchaseRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.created_at.date():
            raise ValueError("PurchaseRecommendation.valid_until must be >= created_at date")
