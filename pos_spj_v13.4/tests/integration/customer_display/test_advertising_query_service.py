"""SET-18 cutover — `AdvertisingQueryService.resolve_active_ads()` and
`RecordContentImpressionUseCase` against a real (in-memory) SQLite
born-clean schema (migration 218).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.customer_display.queries.advertising_query_service import AdvertisingQueryService
from backend.application.customer_display.use_cases.record_content_impression_use_case import (
    RecordContentImpressionUseCase,
)
from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import ContentType, CustomerDisplayMode
from backend.domain.customer_display.policies.campaign_placement_policy import assign_placement
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


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_campaign(conn, *, name="Campaña", starts_at=None, ends_at=None) -> ContentCampaign:
    content = Content.create(title="Promo", content_type=ContentType.TEXT, body="2x1 en refrescos")
    SqliteContentRepository(conn).save(content)
    campaign = ContentCampaign.create(name=name, content_id=content.id, starts_at=starts_at, ends_at=ends_at)
    campaign.submit_for_approval()
    campaign.approve(approved_by_user_id="admin-1")
    campaign.activate(activated_by_user_id="admin-1")
    SqliteContentCampaignRepository(conn).save(campaign)
    conn.commit()
    return campaign


def _slot(conn, *, mode=CustomerDisplayMode.IDLE, order=0) -> AdvertisingSlot:
    slot = AdvertisingSlot.create(code=f"slot-{order}", mode=mode, display_order=order)
    SqliteAdvertisingSlotRepository(conn).save(slot)
    conn.commit()
    return slot


class TestResolveActiveAds:
    def test_resolves_a_real_slot_placement_campaign_content_chain(self, conn):
        campaign = _active_campaign(conn)
        slot = _slot(conn)
        placement = assign_placement(campaign, slot)
        SqliteCampaignPlacementRepository(conn).save(placement)
        conn.commit()

        ads = AdvertisingQueryService(conn).resolve_active_ads(CustomerDisplayMode.IDLE)

        assert len(ads) == 1
        assert ads[0].placement_id == placement.id
        assert ads[0].campaign_id == campaign.id
        assert ads[0].title == "Promo"
        assert ads[0].content_type == "TEXT"
        assert ads[0].body == "2x1 en refrescos"

    def test_empty_when_nothing_configured(self, conn):
        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()

    def test_excludes_inactive_slots(self, conn):
        """A slot can be deactivated AFTER already holding a placement
        (`assign_placement()` itself refuses assigning to an already-
        inactive slot, so this deactivates second, matching the only
        real sequence that can produce this state)."""
        campaign = _active_campaign(conn)
        slot = _slot(conn)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()
        slot.deactivate()
        SqliteAdvertisingSlotRepository(conn).save(slot)
        conn.commit()

        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()

    def test_excludes_a_deactivated_campaign(self, conn):
        campaign = _active_campaign(conn)
        slot = _slot(conn)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()
        campaign.deactivate()
        SqliteContentCampaignRepository(conn).save(campaign)
        conn.commit()

        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()

    def test_excludes_a_campaign_before_its_starts_at(self, conn):
        campaign = _active_campaign(conn, starts_at=_iso(_now() + timedelta(days=1)))
        slot = _slot(conn)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()

        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()

    def test_excludes_a_campaign_after_its_ends_at(self, conn):
        campaign = _active_campaign(conn, ends_at=_iso(_now() - timedelta(days=1)))
        slot = _slot(conn)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()

        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()

    def test_includes_a_campaign_inside_its_window(self, conn):
        campaign = _active_campaign(
            conn, starts_at=_iso(_now() - timedelta(days=1)), ends_at=_iso(_now() + timedelta(days=1)),
        )
        slot = _slot(conn)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()

        assert len(AdvertisingQueryService(conn).resolve_active_ads("IDLE")) == 1

    def test_respects_display_order_across_multiple_slots(self, conn):
        campaign_a = _active_campaign(conn, name="A")
        campaign_b = _active_campaign(conn, name="B")
        slot_second = _slot(conn, order=1)
        slot_first = _slot(conn, order=0)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign_a, slot_second))
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign_b, slot_first))
        conn.commit()

        ads = AdvertisingQueryService(conn).resolve_active_ads("IDLE")
        assert [ad.campaign_id for ad in ads] == [campaign_b.id, campaign_a.id]

    def test_only_returns_ads_for_the_requested_mode(self, conn):
        campaign = _active_campaign(conn)
        slot = _slot(conn, mode=CustomerDisplayMode.CART)
        SqliteCampaignPlacementRepository(conn).save(assign_placement(campaign, slot))
        conn.commit()

        assert AdvertisingQueryService(conn).resolve_active_ads("IDLE") == ()
        assert len(AdvertisingQueryService(conn).resolve_active_ads("CART")) == 1


class TestRecordContentImpressionUseCase:
    def test_records_a_real_impression(self, conn):
        campaign = _active_campaign(conn)
        slot = _slot(conn)
        placement = assign_placement(campaign, slot)
        SqliteCampaignPlacementRepository(conn).save(placement)
        conn.commit()

        RecordContentImpressionUseCase(conn).execute(placement_id=placement.id, duration_shown_seconds=7)

        impressions = SqliteContentImpressionRepository(conn).list_for_placement(placement.id)
        assert len(impressions) == 1
        assert impressions[0].duration_shown_seconds == 7
