"""BusinessRecommendation (§37, BI-18) — the unifying wrapper every
forecasting-domain recommendation type (Purchase/Production/Price/Branch/
StockTransfer, BI-14..BI-17) adapts into for a single approval workflow.

Every field required for §40 explainability is here: `evidence` (what data),
`model_reference` (what model), `rule_reference` (what rule, when a
recommendation comes from a threshold rule rather than a model), `summary`
(why), `expected_impact` (what impact), `confidence` (how sure). Never
"AI recomienda" without the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from decimal import Decimal

from backend.domain.decision_intelligence.enums import (
    BusinessRecommendationType,
    RecommendationStatus,
)
from backend.domain.forecasting.enums import RecommendationPriority
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class BusinessRecommendation:
    id: str
    recommendation_type: BusinessRecommendationType
    target_type: str
    target_id: str
    branch_id: str
    title: str
    summary: str
    evidence: dict[str, str]
    expected_impact: str
    confidence: Decimal
    priority: RecommendationPriority
    status: RecommendationStatus
    valid_from: date
    valid_until: date
    created_at: datetime
    model_reference: str | None = None
    rule_reference: str | None = None

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        for name in ("target_type", "target_id", "branch_id", "title", "summary",
                     "expected_impact"):
            if not getattr(self, name):
                raise ValueError(f"BusinessRecommendation.{name} is required")
        if not self.evidence:
            raise ValueError(
                "BusinessRecommendation.evidence must not be empty (§40: explicabilidad)"
            )
        if not (Decimal("0") <= self.confidence <= Decimal("1")):
            raise ValueError("BusinessRecommendation.confidence must be in [0, 1]")
        if self.valid_until < self.valid_from:
            raise ValueError("BusinessRecommendation.valid_until must be >= valid_from")
        if self.valid_from > self.created_at.date():
            raise ValueError("BusinessRecommendation.valid_from must be <= created_at date")

    def is_terminal(self) -> bool:
        return self.status in (
            RecommendationStatus.REJECTED,
            RecommendationStatus.EXECUTED_EXTERNALLY,
            RecommendationStatus.EXPIRED,
            RecommendationStatus.DISMISSED,
        )
