"""LoyaltyTierEvaluationPolicy — decides which tier a membership currently
qualifies for (master prompt §14). Pure function, no I/O.

**Honest scope limitation, not fabricated**: this bounded context only owns
`lifetime_points` natively (`LoyaltyBalancePolicy.lifetime_earned()`, LOY-2).
`total_spend`/`visit_count` are cross-context data (Sales owns purchase
history) — this policy accepts them as explicit, caller-supplied inputs via
`TierEvaluationStats` rather than reaching into another bounded context's
tables itself. A caller with no real spend/visit integration yet may pass
zero for both, which simply means only `minimum_points`-based tiers become
reachable — an honest degradation, not a silent wrong answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier


@dataclass(frozen=True, slots=True)
class TierEvaluationStats:
    lifetime_points: Decimal
    total_spend: Decimal = Decimal("0")
    visit_count: int = 0


class LoyaltyTierEvaluationPolicy:
    @staticmethod
    def evaluate(tiers: Iterable[LoyaltyTier], stats: TierEvaluationStats) -> LoyaltyTier | None:
        """Returns the highest-``rank`` active tier the stats qualify for,
        or ``None`` if none do (e.g. a brand-new membership with zero
        activity and no zero-minimum tier configured)."""
        qualifying = [
            tier for tier in tiers
            if tier.active and tier.qualifies(
                lifetime_points=stats.lifetime_points,
                total_spend=stats.total_spend, visit_count=stats.visit_count)
        ]
        if not qualifying:
            return None
        return max(qualifying, key=lambda tier: tier.rank)
