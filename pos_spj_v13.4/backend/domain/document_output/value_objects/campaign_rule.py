"""CampaignRule — SET-13 "Rules": a single numeric eligibility condition
a `MarketingCampaign` must satisfy against the caller's context before its
message is eligible to print. Generalizes the legacy hardcoded thresholds
in `core/tickets/ticket_message_engine.py::TicketMessageEngine.build_messages`
(`goal_remaining <= 5`, `points_to_reward <= 50`, `promo_days_left <= 4`)
into configurable data instead of code — the same metric names, not
invented from scratch.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.document_output.enums import RuleComparator
from backend.domain.document_output.exceptions import DocumentInvalidValueError

_COMPARATORS = {
    RuleComparator.LESS_THAN: lambda value, threshold: value < threshold,
    RuleComparator.LESS_THAN_OR_EQUAL: lambda value, threshold: value <= threshold,
    RuleComparator.GREATER_THAN: lambda value, threshold: value > threshold,
    RuleComparator.GREATER_THAN_OR_EQUAL: lambda value, threshold: value >= threshold,
    RuleComparator.EQUAL: lambda value, threshold: value == threshold,
}


@dataclass(frozen=True, slots=True)
class CampaignRule:
    metric: str
    comparator: RuleComparator
    threshold: Decimal

    @classmethod
    def create(cls, *, metric: str, comparator: RuleComparator, threshold: Decimal) -> "CampaignRule":
        if not metric.strip():
            raise DocumentInvalidValueError("metric es obligatorio")
        if isinstance(threshold, bool) or isinstance(threshold, float) or not isinstance(threshold, Decimal):
            raise DocumentInvalidValueError(f"threshold debe ser Decimal, nunca float, recibido {threshold!r}")
        return cls(metric=metric.strip(), comparator=comparator, threshold=threshold)

    def evaluate(self, value: Decimal) -> bool:
        return _COMPARATORS[self.comparator](value, self.threshold)
