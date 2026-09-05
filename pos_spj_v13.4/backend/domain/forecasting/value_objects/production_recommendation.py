"""ProductionRecommendation (§30/§76, BI-15).

Same principle as `PurchaseRecommendation` (§29/BI-14): BI recommends,
Production decides and creates the actual processing order. No execution
method exists on this value object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class ProductionRecommendation:
    id: str
    product_id: str
    branch_id: str
    recommended_production_quantity: Decimal
    recommended_processing_date: date
    expected_demand: Decimal
    current_stock: Decimal
    expected_yield_pct: Decimal | None
    required_raw_material: Decimal | None
    capacity_utilization_pct: Decimal | None
    priority: RecommendationPriority
    confidence: Decimal
    created_at: datetime
    valid_until: date

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.product_id or not self.branch_id:
            raise ValueError("ProductionRecommendation requires product_id and branch_id")
        for name in ("recommended_production_quantity", "expected_demand", "current_stock"):
            if getattr(self, name) < 0:
                raise ValueError(f"ProductionRecommendation.{name} must be >= 0")
        if self.expected_yield_pct is not None and not (Decimal("0") < self.expected_yield_pct <= Decimal("1")):
            raise ValueError("ProductionRecommendation.expected_yield_pct must be in (0, 1] or None")
        if self.required_raw_material is not None and self.required_raw_material < 0:
            raise ValueError("ProductionRecommendation.required_raw_material must be >= 0 or None")
        if self.capacity_utilization_pct is not None and self.capacity_utilization_pct < 0:
            raise ValueError("ProductionRecommendation.capacity_utilization_pct must be >= 0 or None")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("ProductionRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.created_at.date():
            raise ValueError("ProductionRecommendation.valid_until must be >= created_at date")
