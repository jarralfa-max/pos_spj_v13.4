"""LOY-7 — LoyaltyTier / LoyaltyTierHistory / LoyaltyTierEvaluationPolicy
(master prompt §14)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier
from backend.domain.loyalty.entities.loyalty_tier_history import LoyaltyTierHistory
from backend.domain.loyalty.exceptions import InvalidLoyaltyTierError
from backend.domain.loyalty.policies.tier_evaluation_policy import (
    LoyaltyTierEvaluationPolicy,
    TierEvaluationStats,
)
from backend.shared.ids import new_uuid


def _tier(rank: int, minimum_points: str, **overrides) -> LoyaltyTier:
    return LoyaltyTier.create(
        new_uuid(), f"T{rank}", f"Tier {rank}", rank,
        minimum_points=Decimal(minimum_points), **overrides)


class TestLoyaltyTier:
    def test_create_defaults(self):
        tier = _tier(1, "0")
        assert tier.active is True
        assert tier.benefit_multiplier == Decimal("1")

    def test_requires_code_and_name(self):
        with pytest.raises(InvalidLoyaltyTierError):
            LoyaltyTier.create(new_uuid(), "", "Bronce", 1)
        with pytest.raises(InvalidLoyaltyTierError):
            LoyaltyTier.create(new_uuid(), "BRZ", "", 1)

    def test_rejects_float_minimum(self):
        with pytest.raises(InvalidLoyaltyTierError):
            LoyaltyTier.create(new_uuid(), "BRZ", "Bronce", 1, minimum_points=100.0)

    def test_rejects_negative_minimum(self):
        with pytest.raises(InvalidLoyaltyTierError):
            LoyaltyTier.create(new_uuid(), "BRZ", "Bronce", 1, minimum_points=Decimal("-1"))

    def test_qualifies(self):
        tier = _tier(2, "500", minimum_spend=Decimal("1000"), minimum_visits=3)
        assert tier.qualifies(
            lifetime_points=Decimal("600"), total_spend=Decimal("1200"), visit_count=5)
        assert not tier.qualifies(
            lifetime_points=Decimal("100"), total_spend=Decimal("1200"), visit_count=5)

    def test_activate_deactivate(self):
        tier = _tier(1, "0")
        tier.deactivate()
        assert tier.active is False
        tier.activate()
        assert tier.active is True


class TestLoyaltyTierHistory:
    def test_records_change(self):
        entry = LoyaltyTierHistory.record(
            new_uuid(), previous_tier_id=None, new_tier_id=new_uuid(), reason="Primera evaluación")
        assert entry.previous_tier_id is None

    def test_requires_a_real_change(self):
        tier_id = new_uuid()
        with pytest.raises(InvalidLoyaltyTierError):
            LoyaltyTierHistory.record(
                new_uuid(), previous_tier_id=tier_id, new_tier_id=tier_id, reason="x")


class TestLoyaltyTierEvaluationPolicy:
    def test_picks_highest_qualifying_rank(self):
        bronze = _tier(1, "0")
        silver = _tier(2, "500")
        gold = _tier(3, "2000")
        result = LoyaltyTierEvaluationPolicy.evaluate(
            [bronze, silver, gold], TierEvaluationStats(lifetime_points=Decimal("600")))
        assert result.code == silver.code

    def test_returns_none_when_nothing_qualifies(self):
        silver = _tier(2, "500")
        result = LoyaltyTierEvaluationPolicy.evaluate(
            [silver], TierEvaluationStats(lifetime_points=Decimal("10")))
        assert result is None

    def test_ignores_inactive_tiers(self):
        bronze = _tier(1, "0")
        gold = _tier(3, "0")
        gold.deactivate()
        result = LoyaltyTierEvaluationPolicy.evaluate(
            [bronze, gold], TierEvaluationStats(lifetime_points=Decimal("0")))
        assert result.code == bronze.code

    def test_honest_degradation_with_zero_spend_and_visits(self):
        """No spend/visit integration exists yet — passing zero for both is
        honest, not a silent wrong answer; only points-based tiers become
        reachable."""
        points_only = _tier(1, "100")
        spend_gated = _tier(2, "0", minimum_spend=Decimal("5000"))
        result = LoyaltyTierEvaluationPolicy.evaluate(
            [points_only, spend_gated], TierEvaluationStats(lifetime_points=Decimal("150")))
        assert result.code == points_only.code
