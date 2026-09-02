"""SET-13 — "Campaigns"/"Rules": MarketingCampaign + CampaignRule. Pure
domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.enums import MarketingMessageCategory, RuleComparator
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.shared.ids import is_uuidv7


def _rule(**overrides) -> CampaignRule:
    kwargs = dict(metric="goal_remaining", comparator=RuleComparator.LESS_THAN_OR_EQUAL, threshold=Decimal("5"))
    kwargs.update(overrides)
    return CampaignRule.create(**kwargs)


def _campaign(**overrides) -> MarketingCampaign:
    kwargs = dict(
        code="goal_near", category=MarketingMessageCategory.FOMO,
        message_template="Estás a {goal_remaining} compras de tu recompensa.", priority=95, rules=[_rule()],
    )
    kwargs.update(overrides)
    return MarketingCampaign.create(**kwargs)


class TestCampaignRuleCreate:
    def test_requires_metric(self):
        with pytest.raises(DocumentInvalidValueError):
            _rule(metric="   ")

    def test_rejects_float_threshold(self):
        with pytest.raises(DocumentInvalidValueError):
            _rule(threshold=5.0)

    @pytest.mark.parametrize(
        "comparator,threshold,value,expected",
        [
            (RuleComparator.LESS_THAN, Decimal("5"), Decimal("4"), True),
            (RuleComparator.LESS_THAN, Decimal("5"), Decimal("5"), False),
            (RuleComparator.LESS_THAN_OR_EQUAL, Decimal("5"), Decimal("5"), True),
            (RuleComparator.GREATER_THAN, Decimal("5"), Decimal("6"), True),
            (RuleComparator.GREATER_THAN_OR_EQUAL, Decimal("5"), Decimal("5"), True),
            (RuleComparator.EQUAL, Decimal("5"), Decimal("5"), True),
            (RuleComparator.EQUAL, Decimal("5"), Decimal("4"), False),
        ],
    )
    def test_evaluate(self, comparator, threshold, value, expected):
        rule = _rule(comparator=comparator, threshold=threshold)
        assert rule.evaluate(value) is expected


class TestMarketingCampaignCreate:
    def test_mints_uuidv7_and_trims_fields(self):
        campaign = _campaign(code="  goal_near  ")
        assert is_uuidv7(campaign.id)
        assert campaign.code == "goal_near"
        assert campaign.active is True

    def test_requires_code(self):
        with pytest.raises(DocumentInvalidValueError):
            _campaign(code="   ")

    def test_requires_message_template(self):
        with pytest.raises(DocumentInvalidValueError):
            _campaign(message_template="   ")

    def test_defaults_to_no_rules_and_not_requiring_customer(self):
        campaign = MarketingCampaign.create(
            code="new_customer", category=MarketingMessageCategory.CTA, message_template="Regístrate.",
        )
        assert campaign.rules == ()
        assert campaign.requires_customer is False

    def test_activate_deactivate(self):
        campaign = _campaign()
        campaign.deactivate()
        assert campaign.active is False
        campaign.activate()
        assert campaign.active is True


class TestMarketingCampaignMatches:
    def test_inactive_campaign_never_matches(self):
        campaign = _campaign()
        campaign.deactivate()
        assert campaign.matches({"goal_remaining": Decimal("1")}) is False

    def test_matches_when_all_rules_pass(self):
        campaign = _campaign()
        assert campaign.matches({"goal_remaining": Decimal("3")}) is True

    def test_does_not_match_when_a_rule_fails(self):
        campaign = _campaign()
        assert campaign.matches({"goal_remaining": Decimal("10")}) is False

    def test_does_not_match_when_metric_missing_from_context(self):
        campaign = _campaign()
        assert campaign.matches({}) is False

    def test_requires_customer_flag_gates_matching(self):
        campaign = _campaign(requires_customer=True, rules=[])
        assert campaign.matches({}) is False
        assert campaign.matches({"has_customer": False}) is False
        assert campaign.matches({"has_customer": True}) is True

    def test_no_rules_and_no_customer_requirement_always_matches_when_active(self):
        campaign = MarketingCampaign.create(
            code="points_gained", category=MarketingMessageCategory.LOYALTY, message_template="Ganaste puntos.",
        )
        assert campaign.matches({}) is True

    def test_multiple_rules_are_anded(self):
        campaign = _campaign(rules=[
            _rule(metric="goal_remaining", comparator=RuleComparator.LESS_THAN_OR_EQUAL, threshold=Decimal("5")),
            _rule(metric="points_balance", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("0")),
        ])
        assert campaign.matches({"goal_remaining": Decimal("3"), "points_balance": Decimal("10")}) is True
        assert campaign.matches({"goal_remaining": Decimal("3"), "points_balance": Decimal("0")}) is False


class TestMarketingCampaignRenderMessage:
    def test_fills_placeholders_from_context(self):
        campaign = _campaign()
        assert campaign.render_message({"goal_remaining": 3}) == "Estás a 3 compras de tu recompensa."


class TestMarketingCampaignUpdateDetails:
    def test_updates_message_priority_and_requires_customer(self):
        campaign = _campaign()
        campaign.update_details(
            message_template="¡Nuevo mensaje {points_balance}!", priority=50, requires_customer=True,
            rules=[_rule(metric="points_balance")],
        )
        assert campaign.message_template == "¡Nuevo mensaje {points_balance}!"
        assert campaign.priority == 50
        assert campaign.requires_customer is True
        assert campaign.rules[0].metric == "points_balance"

    def test_does_not_change_code_or_category(self):
        campaign = _campaign()
        campaign.update_details(message_template="Otro mensaje.")
        assert campaign.code == "goal_near"
        assert campaign.category is MarketingMessageCategory.FOMO

    def test_requires_message_template(self):
        campaign = _campaign()
        with pytest.raises(DocumentInvalidValueError):
            campaign.update_details(message_template="   ")

    def test_clears_rules_when_given_empty(self):
        campaign = _campaign()
        campaign.update_details(message_template="Mensaje sin reglas.", rules=[])
        assert campaign.rules == ()

    def test_allowed_regardless_of_active_status(self):
        campaign = _campaign()
        campaign.deactivate()
        campaign.update_details(message_template="Editado mientras inactiva.")
        assert campaign.message_template == "Editado mientras inactiva."
        assert campaign.active is False
