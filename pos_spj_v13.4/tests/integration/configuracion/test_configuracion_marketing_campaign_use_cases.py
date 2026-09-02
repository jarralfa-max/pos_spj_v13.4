"""SET-13 cutover — real CRUD for "Campañas de marketing" (Documentos
page card): create/update/activate/deactivate a `MarketingCampaign`.
Against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.use_cases.configuracion.marketing_campaign_use_cases import (
    ChangeMarketingCampaignStatusUseCase,
    CreateMarketingCampaignUseCase,
    MarketingCampaignStatusAction,
    UpdateMarketingCampaignUseCase,
)
from backend.domain.document_output.enums import RuleComparator
from backend.domain.document_output.exceptions import MarketingCampaignNotFoundError, MarketingClaimNotAllowedError
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _create(conn, **overrides):
    kwargs = dict(
        code="goal_near", category="FOMO", message_template="Estás a {goal_remaining} compras.",
        priority=95, rules=[CampaignRule.create(
            metric="goal_remaining", comparator=RuleComparator.LESS_THAN_OR_EQUAL, threshold=Decimal("5"))],
    )
    kwargs.update(overrides)
    return CreateMarketingCampaignUseCase(conn).execute(**kwargs)


class TestCreateMarketingCampaignUseCase:
    def test_creates_and_persists(self, conn):
        campaign = _create(conn)
        assert campaign.code == "goal_near"
        assert SqliteMarketingCampaignRepository(conn).get(campaign.id) is not None

    def test_rejects_fomo_campaign_without_rules(self, conn):
        with pytest.raises(MarketingClaimNotAllowedError):
            _create(conn, rules=[])

    def test_loyalty_campaign_without_rules_is_allowed(self, conn):
        campaign = _create(conn, code="points_gained", category="LOYALTY", rules=[])
        assert campaign.rules == ()


class TestUpdateMarketingCampaignUseCase:
    def test_updates_message_priority_and_rules(self, conn):
        campaign = _create(conn)
        updated = UpdateMarketingCampaignUseCase(conn).execute(
            campaign_id=campaign.id, message_template="Nuevo mensaje.", priority=10,
            requires_customer=True, rules=[CampaignRule.create(
                metric="points_balance", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("0"))],
        )
        assert updated.message_template == "Nuevo mensaje."
        assert updated.priority == 10
        assert updated.requires_customer is True
        fetched = SqliteMarketingCampaignRepository(conn).get(campaign.id)
        assert fetched.message_template == "Nuevo mensaje."

    def test_unknown_campaign_raises(self, conn):
        with pytest.raises(MarketingCampaignNotFoundError):
            UpdateMarketingCampaignUseCase(conn).execute(campaign_id=new_uuid(), message_template="X")

    def test_rejects_removing_rules_from_a_fomo_campaign(self, conn):
        campaign = _create(conn)
        with pytest.raises(MarketingClaimNotAllowedError):
            UpdateMarketingCampaignUseCase(conn).execute(
                campaign_id=campaign.id, message_template="Sin reglas ahora.", rules=[])


class TestChangeMarketingCampaignStatusUseCase:
    def test_deactivate_and_activate(self, conn):
        campaign = _create(conn)
        use_case = ChangeMarketingCampaignStatusUseCase(conn)

        deactivated = use_case.execute(campaign_id=campaign.id, action=MarketingCampaignStatusAction.DEACTIVATE)
        assert deactivated.active is False

        activated = use_case.execute(campaign_id=campaign.id, action=MarketingCampaignStatusAction.ACTIVATE)
        assert activated.active is True

    def test_unknown_campaign_raises(self, conn):
        use_case = ChangeMarketingCampaignStatusUseCase(conn)
        with pytest.raises(MarketingCampaignNotFoundError):
            use_case.execute(campaign_id=new_uuid(), action=MarketingCampaignStatusAction.DEACTIVATE)
