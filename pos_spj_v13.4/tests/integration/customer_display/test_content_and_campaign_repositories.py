"""SET-18 — SqliteContentRepository + SqliteContentCampaignRepository
against a real (in-memory) SQLite born-clean schema (migration 218).
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.content import Content
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import ContentCampaignStatus, ContentType
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
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


@pytest.fixture
def content_repo(conn):
    return SqliteContentRepository(conn)


@pytest.fixture
def campaign_repo(conn):
    return SqliteContentCampaignRepository(conn)


class TestContentRepository:
    def test_save_get_roundtrip(self, conn, content_repo):
        content = Content.create(title="Promo Verano", content_type=ContentType.IMAGE, body="base64...")
        content_repo.save(content)
        conn.commit()

        fetched = content_repo.get(content.id)
        assert fetched.title == "Promo Verano"
        assert fetched.content_type is ContentType.IMAGE
        assert fetched.active is True

    def test_list_active_excludes_inactive(self, conn, content_repo):
        active = Content.create(title="Activo", content_type=ContentType.TEXT, body="Hola")
        inactive = Content.create(title="Inactivo", content_type=ContentType.TEXT, body="Hola")
        inactive.deactivate()
        content_repo.save(active)
        content_repo.save(inactive)
        conn.commit()

        codes = {c.title for c in content_repo.list_active()}
        assert codes == {"Activo"}

    def test_list_all_includes_inactive(self, conn, content_repo):
        active = Content.create(title="Activo", content_type=ContentType.TEXT, body="Hola")
        inactive = Content.create(title="Inactivo", content_type=ContentType.TEXT, body="Hola")
        inactive.deactivate()
        content_repo.save(active)
        content_repo.save(inactive)
        conn.commit()

        titles = {c.title for c in content_repo.list_all()}
        assert titles == {"Activo", "Inactivo"}


class TestContentCampaignRepository:
    def test_save_get_roundtrip(self, conn, content_repo, campaign_repo):
        content = Content.create(title="Promo Verano", content_type=ContentType.IMAGE, body="base64...")
        content_repo.save(content)
        conn.commit()

        campaign = ContentCampaign.create(name="Campaña Verano", content_id=content.id)
        campaign_repo.save(campaign)
        conn.commit()

        fetched = campaign_repo.get(campaign.id)
        assert fetched.name == "Campaña Verano"
        assert fetched.content_id == content.id
        assert fetched.status is ContentCampaignStatus.DRAFT

    def test_full_lifecycle_persists(self, conn, content_repo, campaign_repo):
        content = Content.create(title="Promo Verano", content_type=ContentType.IMAGE, body="base64...")
        content_repo.save(content)
        conn.commit()

        campaign = ContentCampaign.create(name="Campaña Verano", content_id=content.id)
        campaign_repo.save(campaign)
        conn.commit()

        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="admin-1")
        campaign.activate(activated_by_user_id="admin-1")
        campaign_repo.save(campaign)
        conn.commit()

        fetched = campaign_repo.get(campaign.id)
        assert fetched.status is ContentCampaignStatus.ACTIVE
        assert fetched.approved_by_user_id == "admin-1"
        assert fetched.activated_by_user_id == "admin-1"

    def test_list_by_status(self, conn, content_repo, campaign_repo):
        content = Content.create(title="Promo", content_type=ContentType.TEXT, body="Hola")
        content_repo.save(content)
        conn.commit()

        draft = ContentCampaign.create(name="Draft", content_id=content.id)
        pending = ContentCampaign.create(name="Pending", content_id=content.id)
        pending.submit_for_approval()
        campaign_repo.save(draft)
        campaign_repo.save(pending)
        conn.commit()

        drafts = campaign_repo.list_by_status("DRAFT")
        assert [c.id for c in drafts] == [draft.id]

    def test_save_persists_an_updated_schedule(self, conn, content_repo, campaign_repo):
        """SET-18 repegado: `update_schedule()` is a new mutation this
        round added — the UPSERT's UPDATE SET clause originally never
        touched `starts_at`/`ends_at` at all (no caller ever needed it
        before), so a second `save()` silently dropped a real schedule
        edit. Found by `TestUpdateContentCampaignUseCase`, fixed here."""
        content = Content.create(title="Promo", content_type=ContentType.TEXT, body="Hola")
        content_repo.save(content)
        conn.commit()
        campaign = ContentCampaign.create(name="Campaña", content_id=content.id)
        campaign_repo.save(campaign)
        conn.commit()

        campaign.update_schedule(starts_at="2026-08-01T00:00:00+00:00", ends_at="2026-09-01T00:00:00+00:00")
        campaign_repo.save(campaign)
        conn.commit()

        fetched = campaign_repo.get(campaign.id)
        assert fetched.starts_at == "2026-08-01T00:00:00+00:00"
        assert fetched.ends_at == "2026-09-01T00:00:00+00:00"

    def test_list_all_returns_every_status(self, conn, content_repo, campaign_repo):
        content = Content.create(title="Promo", content_type=ContentType.TEXT, body="Hola")
        content_repo.save(content)
        conn.commit()

        draft = ContentCampaign.create(name="Draft", content_id=content.id)
        pending = ContentCampaign.create(name="Pending", content_id=content.id)
        pending.submit_for_approval()
        campaign_repo.save(draft)
        campaign_repo.save(pending)
        conn.commit()

        names = {c.name for c in campaign_repo.list_all()}
        assert names == {"Draft", "Pending"}
