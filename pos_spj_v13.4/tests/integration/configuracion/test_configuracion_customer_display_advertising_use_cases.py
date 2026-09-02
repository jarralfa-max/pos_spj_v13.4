"""SET-18 cutover — real CRUD for the "Pantalla del cliente" section's
advertising cards (Contenido/Campañas/Slots/Asignaciones). Against a
real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.customer_display_advertising_use_cases import (
    AdvertisingSlotStatusAction,
    AssignCampaignPlacementUseCase,
    ChangeAdvertisingSlotStatusUseCase,
    ChangeContentCampaignStatusUseCase,
    ChangeContentStatusUseCase,
    ContentCampaignStatusAction,
    ContentStatusAction,
    CreateAdvertisingSlotUseCase,
    CreateContentCampaignUseCase,
    CreateContentUseCase,
    UnassignCampaignPlacementUseCase,
    UpdateAdvertisingSlotUseCase,
    UpdateContentCampaignUseCase,
    UpdateContentUseCase,
)
from backend.domain.customer_display.enums import ContentCampaignStatus, ContentType, CustomerDisplayMode
from backend.domain.customer_display.exceptions import (
    CampaignPlacementNotAllowedError,
    CampaignPlacementSlotOccupiedError,
    ContentCampaignApprovalSegregationError,
    CustomerDisplayNotFoundError,
)
from backend.infrastructure.db.repositories.customer_display.advertising_slot_repository import (
    SqliteAdvertisingSlotRepository,
)
from backend.infrastructure.db.repositories.customer_display.campaign_placement_repository import (
    SqliteCampaignPlacementRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_campaign_repository import (
    SqliteContentCampaignRepository,
)
from backend.infrastructure.db.repositories.customer_display.content_repository import (
    SqliteContentRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _content(conn, **overrides):
    kwargs = dict(title="Promo", content_type=ContentType.TEXT, body="2x1", duration_seconds=10)
    kwargs.update(overrides)
    return CreateContentUseCase(conn).execute(**kwargs)


def _active_campaign(conn, **overrides):
    content = _content(conn)
    kwargs = dict(name="Campaña Verano", content_id=content.id, created_by_user_id="creator-1")
    kwargs.update(overrides)
    campaign = CreateContentCampaignUseCase(conn).execute(**kwargs)
    ChangeContentCampaignStatusUseCase(conn).execute(
        campaign_id=campaign.id, action=ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL)
    ChangeContentCampaignStatusUseCase(conn).execute(
        campaign_id=campaign.id, action=ContentCampaignStatusAction.APPROVE, actor_user_id="approver-1")
    return ChangeContentCampaignStatusUseCase(conn).execute(
        campaign_id=campaign.id, action=ContentCampaignStatusAction.ACTIVATE, actor_user_id="approver-1")


class TestContentUseCases:
    def test_create_persists(self, conn):
        content = _content(conn)
        assert SqliteContentRepository(conn).get(content.id) is not None

    def test_update_persists(self, conn):
        content = _content(conn)
        updated = UpdateContentUseCase(conn).execute(
            content_id=content.id, title="Nuevo", body="nuevo cuerpo", duration_seconds=20)
        assert updated.title == "Nuevo"
        assert SqliteContentRepository(conn).get(content.id).duration_seconds == 20

    def test_update_unknown_content_raises(self, conn):
        with pytest.raises(CustomerDisplayNotFoundError):
            UpdateContentUseCase(conn).execute(content_id=new_uuid(), title="X", body="Y")

    def test_change_status_activate_deactivate(self, conn):
        content = _content(conn)
        use_case = ChangeContentStatusUseCase(conn)
        deactivated = use_case.execute(content_id=content.id, action=ContentStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(content_id=content.id, action=ContentStatusAction.ACTIVATE)
        assert activated.active is True


class TestContentCampaignUseCases:
    def test_create_persists(self, conn):
        content = _content(conn)
        campaign = CreateContentCampaignUseCase(conn).execute(name="Campaña", content_id=content.id)
        assert SqliteContentCampaignRepository(conn).get(campaign.id) is not None

    def test_update_schedule_persists(self, conn):
        content = _content(conn)
        campaign = CreateContentCampaignUseCase(conn).execute(name="Campaña", content_id=content.id)
        updated = UpdateContentCampaignUseCase(conn).execute(
            campaign_id=campaign.id, starts_at="2026-08-01T00:00:00+00:00",
            ends_at="2026-09-01T00:00:00+00:00")
        assert updated.starts_at == "2026-08-01T00:00:00+00:00"
        assert SqliteContentCampaignRepository(conn).get(campaign.id).ends_at == "2026-09-01T00:00:00+00:00"

    def test_update_unknown_campaign_raises(self, conn):
        with pytest.raises(CustomerDisplayNotFoundError):
            UpdateContentCampaignUseCase(conn).execute(campaign_id=new_uuid())

    def test_full_lifecycle_through_the_use_case(self, conn):
        campaign = _active_campaign(conn)
        assert campaign.status is ContentCampaignStatus.ACTIVE
        assert SqliteContentCampaignRepository(conn).get(campaign.id).status is ContentCampaignStatus.ACTIVE

    def test_reject_requires_a_reason_and_returns_to_draft(self, conn):
        content = _content(conn)
        campaign = CreateContentCampaignUseCase(conn).execute(name="Campaña", content_id=content.id)
        ChangeContentCampaignStatusUseCase(conn).execute(
            campaign_id=campaign.id, action=ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL)
        rejected = ChangeContentCampaignStatusUseCase(conn).execute(
            campaign_id=campaign.id, action=ContentCampaignStatusAction.REJECT, reason="No autorizado")
        assert rejected.status is ContentCampaignStatus.DRAFT
        assert rejected.reason == "No autorizado"

    def test_approve_by_the_creator_raises_segregation_error(self, conn):
        content = _content(conn)
        campaign = CreateContentCampaignUseCase(conn).execute(
            name="Campaña", content_id=content.id, created_by_user_id="user-1")
        ChangeContentCampaignStatusUseCase(conn).execute(
            campaign_id=campaign.id, action=ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL)
        with pytest.raises(ContentCampaignApprovalSegregationError):
            ChangeContentCampaignStatusUseCase(conn).execute(
                campaign_id=campaign.id, action=ContentCampaignStatusAction.APPROVE, actor_user_id="user-1")

    def test_unknown_campaign_raises(self, conn):
        with pytest.raises(CustomerDisplayNotFoundError):
            ChangeContentCampaignStatusUseCase(conn).execute(
                campaign_id=new_uuid(), action=ContentCampaignStatusAction.SUBMIT_FOR_APPROVAL)


class TestAdvertisingSlotUseCases:
    def test_create_persists(self, conn):
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        assert SqliteAdvertisingSlotRepository(conn).get(slot.id) is not None

    def test_update_display_order_persists(self, conn):
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        updated = UpdateAdvertisingSlotUseCase(conn).execute(slot_id=slot.id, display_order=9)
        assert updated.display_order == 9
        assert SqliteAdvertisingSlotRepository(conn).get(slot.id).display_order == 9

    def test_update_unknown_slot_raises(self, conn):
        with pytest.raises(CustomerDisplayNotFoundError):
            UpdateAdvertisingSlotUseCase(conn).execute(slot_id=new_uuid(), display_order=1)

    def test_change_status_activate_deactivate(self, conn):
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        use_case = ChangeAdvertisingSlotStatusUseCase(conn)
        deactivated = use_case.execute(slot_id=slot.id, action=AdvertisingSlotStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(slot_id=slot.id, action=AdvertisingSlotStatusAction.ACTIVATE)
        assert activated.active is True


class TestCampaignPlacementUseCases:
    def test_assign_persists_a_real_placement(self, conn):
        campaign = _active_campaign(conn)
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        placement = AssignCampaignPlacementUseCase(conn).execute(
            campaign_id=campaign.id, slot_id=slot.id, assigned_by_user_id="admin-1")
        assert SqliteCampaignPlacementRepository(conn).get(placement.id).active is True

    def test_assign_a_non_active_campaign_raises_the_domain_error(self, conn):
        content = _content(conn)
        draft_campaign = CreateContentCampaignUseCase(conn).execute(name="Draft", content_id=content.id)
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        with pytest.raises(CampaignPlacementNotAllowedError):
            AssignCampaignPlacementUseCase(conn).execute(campaign_id=draft_campaign.id, slot_id=slot.id)

    def test_assigning_to_an_already_occupied_slot_raises_cleanly(self, conn):
        """Never lets the schema's partial-unique-index IntegrityError
        reach the UI — same discipline `AssignDeviceUseCase` (SET-7)
        already established for `WorkstationDeviceAssignment`."""
        campaign_a = _active_campaign(conn, name="A")
        campaign_b = _active_campaign(conn, name="B")
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        AssignCampaignPlacementUseCase(conn).execute(campaign_id=campaign_a.id, slot_id=slot.id)

        with pytest.raises(CampaignPlacementSlotOccupiedError):
            AssignCampaignPlacementUseCase(conn).execute(campaign_id=campaign_b.id, slot_id=slot.id)

    def test_unassign_then_reassign_succeeds(self, conn):
        campaign_a = _active_campaign(conn, name="A")
        campaign_b = _active_campaign(conn, name="B")
        slot = CreateAdvertisingSlotUseCase(conn).execute(code="idle_main", mode=CustomerDisplayMode.IDLE)
        first = AssignCampaignPlacementUseCase(conn).execute(campaign_id=campaign_a.id, slot_id=slot.id)

        UnassignCampaignPlacementUseCase(conn).execute(placement_id=first.id)
        second = AssignCampaignPlacementUseCase(conn).execute(campaign_id=campaign_b.id, slot_id=slot.id)

        assert SqliteCampaignPlacementRepository(conn).get(first.id).active is False
        assert SqliteCampaignPlacementRepository(conn).get(second.id).active is True

    def test_unassign_unknown_placement_raises(self, conn):
        with pytest.raises(CustomerDisplayNotFoundError):
            UnassignCampaignPlacementUseCase(conn).execute(placement_id=new_uuid())
