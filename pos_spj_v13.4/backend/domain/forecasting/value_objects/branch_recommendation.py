"""BranchRecommendation / StockTransferRecommendation (§31/§74/§77, BI-17).

BI observes branch performance and recommends; it never opens/closes a
branch, never moves stock itself (§31: "No cerrar o abrir sucursales
automáticamente"). Transfers decide and execute (§74: "Transferencias
decide").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import validate_uuidv7


class BranchRecommendationType(str, Enum):
    """§77 — only INCREASE_STOCK/REDUCE_STOCK/TRANSFER_STOCK are actually
    produced by `BranchIntelligenceService` in this phase (derivable from
    `InventoryForecast` alone); the other 5 require signals (staffing,
    schedules, pricing competitiveness, floor-capacity data) this pipeline
    doesn't have yet — reserved vocabulary, not fabricated recommendations."""
    INCREASE_STOCK = "INCREASE_STOCK"
    REDUCE_STOCK = "REDUCE_STOCK"
    CHANGE_ASSORTMENT = "CHANGE_ASSORTMENT"
    REVIEW_STAFFING = "REVIEW_STAFFING"
    REVIEW_HOURS = "REVIEW_HOURS"
    TRANSFER_STOCK = "TRANSFER_STOCK"
    REVIEW_PRICING = "REVIEW_PRICING"
    CAPACITY_EXPANSION = "CAPACITY_EXPANSION"


@dataclass(frozen=True, slots=True)
class BranchRecommendation:
    id: str
    branch_id: str
    recommendation_type: BranchRecommendationType
    reason: str
    affected_product_ids: tuple[str, ...]
    priority: RecommendationPriority
    confidence: Decimal
    created_at: datetime
    valid_until: date

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.branch_id:
            raise ValueError("BranchRecommendation requires branch_id")
        if not self.reason:
            raise ValueError("BranchRecommendation.reason is required (§40: explicabilidad)")
        if not self.affected_product_ids:
            raise ValueError("BranchRecommendation.affected_product_ids must not be empty")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("BranchRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.created_at.date():
            raise ValueError("BranchRecommendation.valid_until must be >= created_at date")


@dataclass(frozen=True, slots=True)
class StockTransferRecommendation:
    """§74 — a surplus at `source_branch_id` covering a deficit at
    `destination_branch_id` for the same product."""
    id: str
    product_id: str
    source_branch_id: str
    destination_branch_id: str
    suggested_quantity: Decimal
    priority: RecommendationPriority
    confidence: Decimal
    created_at: datetime
    valid_until: date

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.product_id:
            raise ValueError("StockTransferRecommendation requires product_id")
        if not self.source_branch_id or not self.destination_branch_id:
            raise ValueError("StockTransferRecommendation requires both branch ids")
        if self.source_branch_id == self.destination_branch_id:
            raise ValueError("StockTransferRecommendation source and destination must differ")
        if self.suggested_quantity <= 0:
            raise ValueError("StockTransferRecommendation.suggested_quantity must be > 0")
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("StockTransferRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.created_at.date():
            raise ValueError("StockTransferRecommendation.valid_until must be >= created_at date")
