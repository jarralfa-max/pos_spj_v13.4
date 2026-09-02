"""SET-13 — SqliteMarketingCampaignRepository against a real (in-memory)
SQLite born-clean schema (migration 215).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.entities.marketing_campaign import MarketingCampaign
from backend.domain.document_output.enums import MarketingMessageCategory, RuleComparator
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.repositories.document_output.marketing_campaign_repository import (
    SqliteMarketingCampaignRepository,
)
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def repo(conn):
    return SqliteMarketingCampaignRepository(conn)


def _campaign(**overrides) -> MarketingCampaign:
    kwargs = dict(
        code="goal_near", category=MarketingMessageCategory.FOMO,
        message_template="Estás a {goal_remaining} compras de tu recompensa.", priority=95,
        rules=[CampaignRule.create(
            metric="goal_remaining", comparator=RuleComparator.LESS_THAN_OR_EQUAL, threshold=Decimal("5"),
        )],
    )
    kwargs.update(overrides)
    return MarketingCampaign.create(**kwargs)


class TestSaveAndGet:
    def test_save_get_roundtrip_preserves_rules(self, conn, repo):
        campaign = _campaign()
        repo.save(campaign)
        conn.commit()

        fetched = repo.get(campaign.id)
        assert fetched.id == campaign.id
        assert fetched.code == "goal_near"
        assert fetched.category is MarketingMessageCategory.FOMO
        assert len(fetched.rules) == 1
        assert fetched.rules[0].metric == "goal_remaining"
        assert fetched.rules[0].comparator is RuleComparator.LESS_THAN_OR_EQUAL
        assert fetched.rules[0].threshold == Decimal("5")

    def test_get_by_code(self, conn, repo):
        campaign = _campaign()
        repo.save(campaign)
        conn.commit()
        assert repo.get_by_code("goal_near").id == campaign.id
        assert repo.get_by_code("does-not-exist") is None

    def test_code_is_unique(self, conn, repo):
        import sqlite3
        repo.save(_campaign())
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(_campaign())
            conn.commit()
        conn.rollback()

    def test_upsert_updates_in_place(self, conn, repo):
        campaign = _campaign()
        repo.save(campaign)
        conn.commit()

        campaign.deactivate()
        repo.save(campaign)
        conn.commit()

        assert repo.get(campaign.id).active is False

    def test_multiple_rules_round_trip_in_order(self, conn, repo):
        campaign = _campaign(rules=[
            CampaignRule.create(metric="goal_remaining", comparator=RuleComparator.LESS_THAN_OR_EQUAL, threshold=Decimal("5")),
            CampaignRule.create(metric="points_balance", comparator=RuleComparator.GREATER_THAN, threshold=Decimal("0")),
        ])
        repo.save(campaign)
        conn.commit()

        fetched = repo.get(campaign.id)
        assert [r.metric for r in fetched.rules] == ["goal_remaining", "points_balance"]


class TestListActive:
    def test_list_active_excludes_inactive(self, conn, repo):
        active = _campaign(code="active_one")
        inactive = _campaign(code="inactive_one")
        inactive.deactivate()
        repo.save(active)
        repo.save(inactive)
        conn.commit()

        codes = {c.code for c in repo.list_active()}
        assert codes == {"active_one"}

    def test_list_active_orders_by_priority_desc(self, conn, repo):
        low = _campaign(code="low", priority=10)
        high = _campaign(code="high", priority=90)
        repo.save(low)
        repo.save(high)
        conn.commit()

        assert [c.code for c in repo.list_active()] == ["high", "low"]

    def test_list_active_by_category(self, conn, repo):
        fomo = _campaign(code="fomo_one", category=MarketingMessageCategory.FOMO)
        loyalty = _campaign(
            code="loyalty_one", category=MarketingMessageCategory.LOYALTY, rules=[],
        )
        repo.save(fomo)
        repo.save(loyalty)
        conn.commit()

        fomo_results = repo.list_active_by_category(MarketingMessageCategory.FOMO)
        assert [c.code for c in fomo_results] == ["fomo_one"]
        loyalty_results = repo.list_active_by_category(MarketingMessageCategory.LOYALTY)
        assert [c.code for c in loyalty_results] == ["loyalty_one"]

    def test_list_active_by_category_excludes_inactive(self, conn, repo):
        campaign = _campaign()
        campaign.deactivate()
        repo.save(campaign)
        conn.commit()
        assert repo.list_active_by_category(MarketingMessageCategory.FOMO) == []


class TestListAll:
    def test_list_all_includes_inactive(self, conn, repo):
        active = _campaign(code="active_one")
        inactive = _campaign(code="inactive_one")
        inactive.deactivate()
        repo.save(active)
        repo.save(inactive)
        conn.commit()

        codes = {c.code for c in repo.list_all()}
        assert codes == {"active_one", "inactive_one"}
