"""SET-18 — SqliteAdvertisingSlotRepository + SqliteCampaignPlacementRepository
+ SqliteContentImpressionRepository against a real (in-memory) SQLite
born-clean schema (migration 218). Also proves
`policies/campaign_placement_policy.assign_placement()` end to end
against persisted entities.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.entities.content_impression import ContentImpression
from backend.domain.customer_display.enums import ContentType, CustomerDisplayMode
from backend.domain.customer_display.policies.campaign_placement_policy import assign_placement
from backend.domain.customer_display.policies.impression_metrics_policy import summarize_impressions
from backend.infrastructure.db.repositories.customer_display.advertising_slot_repository import (
    SqliteAdvertisingSlotRepository,
)
from backend.infrastructure.db.repositories.customer_display.campaign_placement_repository import (
    SqliteCampaignPlacementRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_impression_repository import (
    SqliteContentImpressionRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_repository import (
    SqliteContentRepository,
)
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _active_campaign(conn) -> ContentCampaign:
    content = Content.create(title="Promo Verano", content_type=ContentType.IMAGE, body="base64...")
    SqliteContentRepository(conn).save(content)
    campaign = ContentCampaign.create(name="Campaña Verano", content_id=content.id)
    campaign.submit_for_approval()
    campaign.approve(approved_by_user_id="admin-1")
    campaign.activate(activated_by_user_id="admin-1")
    SqliteContentCampaignRepository(conn).save(campaign)
    conn.commit()
    return campaign


class TestAdvertisingSlotRepository:
    def test_save_get_roundtrip(self, conn):
        repo = SqliteAdvertisingSlotRepository(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        repo.save(slot)
        conn.commit()

        fetched = repo.get(slot.id)
        assert fetched.code == "IDLE_MAIN_BANNER"
        assert fetched.mode is CustomerDisplayMode.IDLE

    def test_get_by_code(self, conn):
        repo = SqliteAdvertisingSlotRepository(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        repo.save(slot)
        conn.commit()
        assert repo.get_by_code("idle_main_banner").id == slot.id
        assert repo.get_by_code("does-not-exist") is None

    def test_list_by_mode_ordered_by_display_order(self, conn):
        repo = SqliteAdvertisingSlotRepository(conn)
        second = AdvertisingSlot.create(code="idle_footer", mode=CustomerDisplayMode.IDLE, display_order=1)
        first = AdvertisingSlot.create(code="idle_banner", mode=CustomerDisplayMode.IDLE, display_order=0)
        repo.save(second)
        repo.save(first)
        conn.commit()

        ordered = repo.list_by_mode(CustomerDisplayMode.IDLE)
        assert [s.id for s in ordered] == [first.id, second.id]

    def test_list_all_includes_every_mode(self, conn):
        repo = SqliteAdvertisingSlotRepository(conn)
        idle = AdvertisingSlot.create(code="idle_banner", mode=CustomerDisplayMode.IDLE)
        cart = AdvertisingSlot.create(code="cart_banner", mode=CustomerDisplayMode.CART)
        repo.save(idle)
        repo.save(cart)
        conn.commit()

        codes = {s.code for s in repo.list_all()}
        assert codes == {"IDLE_BANNER", "CART_BANNER"}


class TestCampaignPlacementRepositoryAndPolicy:
    def test_assign_placement_end_to_end(self, conn):
        campaign = _active_campaign(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        SqliteAdvertisingSlotRepository(conn).save(slot)
        conn.commit()

        placement = assign_placement(campaign, slot, assigned_by_user_id="admin-1")
        placement_repo = SqliteCampaignPlacementRepository(conn)
        placement_repo.save(placement)
        conn.commit()

        fetched = placement_repo.get(placement.id)
        assert fetched.campaign_id == campaign.id
        assert fetched.slot_id == slot.id
        assert fetched.active is True

    def test_unique_index_blocks_two_active_placements_for_same_slot(self, conn):
        campaign_a = _active_campaign(conn)
        campaign_b = _active_campaign(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        SqliteAdvertisingSlotRepository(conn).save(slot)
        conn.commit()

        placement_repo = SqliteCampaignPlacementRepository(conn)
        placement_repo.save(assign_placement(campaign_a, slot))
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            placement_repo.save(assign_placement(campaign_b, slot))
            conn.commit()
        conn.rollback()

    def test_unassigning_allows_a_new_active_placement_for_the_same_slot(self, conn):
        campaign_a = _active_campaign(conn)
        campaign_b = _active_campaign(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        SqliteAdvertisingSlotRepository(conn).save(slot)
        conn.commit()

        placement_repo = SqliteCampaignPlacementRepository(conn)
        first = assign_placement(campaign_a, slot)
        placement_repo.save(first)
        conn.commit()

        first.unassign()
        placement_repo.save(first)
        conn.commit()

        second = assign_placement(campaign_b, slot)
        placement_repo.save(second)
        conn.commit()

        assert placement_repo.get_active_for_slot(slot.id).id == second.id

    def test_list_for_campaign(self, conn):
        campaign = _active_campaign(conn)
        slot_a = AdvertisingSlot.create(code="idle_banner", mode=CustomerDisplayMode.IDLE)
        slot_b = AdvertisingSlot.create(code="thank_you_banner", mode=CustomerDisplayMode.THANK_YOU)
        SqliteAdvertisingSlotRepository(conn).save(slot_a)
        SqliteAdvertisingSlotRepository(conn).save(slot_b)
        conn.commit()

        placement_repo = SqliteCampaignPlacementRepository(conn)
        placement_repo.save(assign_placement(campaign, slot_a))
        placement_repo.save(assign_placement(campaign, slot_b))
        conn.commit()

        assert len(placement_repo.list_for_campaign(campaign.id)) == 2

    def test_list_all_returns_every_placement(self, conn):
        campaign = _active_campaign(conn)
        slot_a = AdvertisingSlot.create(code="idle_banner", mode=CustomerDisplayMode.IDLE)
        slot_b = AdvertisingSlot.create(code="thank_you_banner", mode=CustomerDisplayMode.THANK_YOU)
        SqliteAdvertisingSlotRepository(conn).save(slot_a)
        SqliteAdvertisingSlotRepository(conn).save(slot_b)
        conn.commit()

        placement_repo = SqliteCampaignPlacementRepository(conn)
        placement_repo.save(assign_placement(campaign, slot_a))
        placement_repo.save(assign_placement(campaign, slot_b))
        conn.commit()

        assert len(placement_repo.list_all()) == 2


class TestContentImpressionRepositoryAndMetrics:
    def test_record_and_summarize_end_to_end(self, conn):
        campaign = _active_campaign(conn)
        slot = AdvertisingSlot.create(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
        SqliteAdvertisingSlotRepository(conn).save(slot)
        conn.commit()

        placement = assign_placement(campaign, slot)
        SqliteCampaignPlacementRepository(conn).save(placement)
        conn.commit()

        impression_repo = SqliteContentImpressionRepository(conn)
        for duration in (10, 20, 15):
            impression_repo.save(ContentImpression.record(placement_id=placement.id, duration_shown_seconds=duration))
        conn.commit()

        impressions = impression_repo.list_for_placement(placement.id)
        assert len(impressions) == 3

        summary = summarize_impressions(impressions)
        assert summary.total_impressions == 3
        assert summary.total_duration_seconds == 45

    def test_list_for_placement_returns_empty_when_none_recorded(self, conn):
        impression_repo = SqliteContentImpressionRepository(conn)
        assert impression_repo.list_for_placement("nonexistent") == []
