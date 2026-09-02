"""SET-13 — "FOMO policy": marketing_claim_validation_policy.
assert_responsible_claim/select_messages. Pure domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.enums import MarketingMessageCategory, RuleComparator
from backend.domain.document_output.exceptions import MarketingClaimNotAllowedError
from backend.domain.document_output.policies.marketing_claim_validation_policy import (
    assert_responsible_claim,
    select_messages,
)
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule


def _rule(metric: str, comparator: RuleComparator, threshold: str) -> CampaignRule:
    return CampaignRule.create(metric=metric, comparator=comparator, threshold=Decimal(threshold))


class TestAssertResponsibleClaim:
    def test_fomo_with_no_rules_is_rejected(self):
        campaign = MarketingCampaign.create(
            code="buy_now", category=MarketingMessageCategory.FOMO, message_template="¡Compra ya!",
        )
        with pytest.raises(MarketingClaimNotAllowedError):
            assert_responsible_claim(campaign)

    def test_fomo_with_at_least_one_rule_is_allowed(self):
        campaign = MarketingCampaign.create(
            code="goal_near", category=MarketingMessageCategory.FOMO, message_template="Estás cerca.",
            rules=[_rule("goal_remaining", RuleComparator.LESS_THAN_OR_EQUAL, "5")],
        )
        assert_responsible_claim(campaign)  # does not raise

    def test_loyalty_and_cta_are_exempt_even_without_rules(self):
        loyalty = MarketingCampaign.create(
            code="points_gained", category=MarketingMessageCategory.LOYALTY, message_template="Ganaste puntos.",
        )
        cta = MarketingCampaign.create(
            code="new_customer", category=MarketingMessageCategory.CTA, message_template="Regístrate.",
        )
        assert_responsible_claim(loyalty)  # does not raise
        assert_responsible_claim(cta)  # does not raise


class TestSelectMessages:
    def _fomo_rule_campaign(self, code: str, metric: str, threshold: str, priority: int) -> MarketingCampaign:
        return MarketingCampaign.create(
            code=code, category=MarketingMessageCategory.FOMO, message_template=f"{code} claim",
            priority=priority, rules=[_rule(metric, RuleComparator.LESS_THAN_OR_EQUAL, threshold)],
        )

    def test_only_matching_campaigns_are_selected(self):
        matches = self._fomo_rule_campaign("goal_near", "goal_remaining", "5", 90)
        does_not_match = self._fomo_rule_campaign("promo_expiring", "promo_days_left", "4", 98)
        selected = select_messages([matches, does_not_match], {"goal_remaining": Decimal("3")})
        assert [c.code for c in selected] == ["goal_near"]

    def test_higher_priority_first_within_category(self):
        low = self._fomo_rule_campaign("low", "goal_remaining", "5", 10)
        high = self._fomo_rule_campaign("high", "goal_remaining", "5", 90)
        selected = select_messages([low, high], {"goal_remaining": Decimal("1")})
        assert [c.code for c in selected] == ["high", "low"]

    def test_caps_per_category(self):
        campaigns = [
            self._fomo_rule_campaign(f"c{i}", "goal_remaining", "5", i) for i in range(5)
        ]
        selected = select_messages(
            campaigns, {"goal_remaining": Decimal("1")}, max_per_category={MarketingMessageCategory.FOMO: 2},
        )
        assert len(selected) == 2
        assert [c.code for c in selected] == ["c4", "c3"]

    def test_no_limit_means_unbounded(self):
        campaigns = [
            self._fomo_rule_campaign(f"c{i}", "goal_remaining", "5", i) for i in range(3)
        ]
        selected = select_messages(campaigns, {"goal_remaining": Decimal("1")})
        assert len(selected) == 3

    def test_caps_apply_independently_per_category(self):
        fomo = self._fomo_rule_campaign("fomo1", "goal_remaining", "5", 50)
        loyalty = MarketingCampaign.create(
            code="points_gained", category=MarketingMessageCategory.LOYALTY, message_template="Ganaste puntos.",
        )
        selected = select_messages(
            [fomo, loyalty], {"goal_remaining": Decimal("1")},
            max_per_category={MarketingMessageCategory.FOMO: 0},
        )
        assert [c.code for c in selected] == ["points_gained"]

    def test_inactive_campaigns_are_never_selected(self):
        campaign = self._fomo_rule_campaign("goal_near", "goal_remaining", "5", 90)
        campaign.deactivate()
        selected = select_messages([campaign], {"goal_remaining": Decimal("1")})
        assert selected == ()

    def test_matching_but_irresponsible_fomo_claim_raises(self):
        # Constructed to bypass MarketingCampaign.create's own validation
        # (there isn't one preventing a rule-less FOMO campaign at
        # construction time — assert_responsible_claim is the gate) so
        # select_messages must still catch it if one ever slips into the
        # candidate list (e.g. a rule was removed via an admin edit).
        campaign = MarketingCampaign.create(
            code="buy_now", category=MarketingMessageCategory.FOMO, message_template="¡Compra ya!",
        )
        with pytest.raises(MarketingClaimNotAllowedError):
            select_messages([campaign], {})
