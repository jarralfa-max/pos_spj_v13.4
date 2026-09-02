"""SET-18 — "Placements" gated by "Approval": AdvertisingSlot,
CampaignPlacement, campaign_placement_policy.assign_placement. Pure
domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.advertising_slot import AdvertisingSlot
from backend.domain.customer_display.entities.campaign_placement import CampaignPlacement
from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import CustomerDisplayMode
from backend.domain.customer_display.exceptions import (
    AssignmentAlreadyInactiveError,
    CampaignPlacementNotAllowedError,
    CustomerDisplayInvalidValueError,
)
from backend.domain.customer_display.policies.campaign_placement_policy import assign_placement
from backend.shared.ids import is_uuidv7, new_uuid


def _slot(**overrides) -> AdvertisingSlot:
    kwargs = dict(code="idle_main_banner", mode=CustomerDisplayMode.IDLE)
    kwargs.update(overrides)
    return AdvertisingSlot.create(**kwargs)


def _active_campaign() -> ContentCampaign:
    campaign = ContentCampaign.create(name="Campaña Verano", content_id=new_uuid())
    campaign.submit_for_approval()
    campaign.approve(approved_by_user_id="admin-1")
    campaign.activate(activated_by_user_id="admin-1")
    return campaign


class TestAdvertisingSlotCreate:
    def test_mints_uuidv7_and_normalizes_code(self):
        slot = _slot(code="  idle_main_banner  ")
        assert is_uuidv7(slot.id)
        assert slot.code == "IDLE_MAIN_BANNER"
        assert slot.active is True

    def test_requires_code(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _slot(code="   ")

    @pytest.mark.parametrize("order", [-1, 1.5, True])
    def test_rejects_invalid_display_order(self, order):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _slot(display_order=order)

    def test_activate_deactivate(self):
        slot = _slot()
        slot.deactivate()
        assert slot.active is False
        slot.activate()
        assert slot.active is True

    def test_update_display_order(self):
        slot = _slot(display_order=0)
        slot.update_display_order(5)
        assert slot.display_order == 5

    @pytest.mark.parametrize("order", [-1, 1.5, True])
    def test_update_display_order_rejects_invalid_values(self, order):
        slot = _slot()
        with pytest.raises(CustomerDisplayInvalidValueError):
            slot.update_display_order(order)


class TestCampaignPlacementAssignUnassign:
    def test_assign_mints_uuidv7(self):
        placement = CampaignPlacement.assign(campaign_id=new_uuid(), slot_id=new_uuid())
        assert is_uuidv7(placement.id)
        assert placement.active is True

    def test_unassign_marks_inactive(self):
        placement = CampaignPlacement.assign(campaign_id=new_uuid(), slot_id=new_uuid())
        placement.unassign()
        assert placement.active is False
        assert placement.unassigned_at is not None

    def test_unassign_twice_raises(self):
        placement = CampaignPlacement.assign(campaign_id=new_uuid(), slot_id=new_uuid())
        placement.unassign()
        with pytest.raises(AssignmentAlreadyInactiveError):
            placement.unassign()


class TestAssignPlacementPolicy:
    def test_active_campaign_can_be_placed(self):
        campaign = _active_campaign()
        slot = _slot()
        placement = assign_placement(campaign, slot, assigned_by_user_id="admin-1")
        assert placement.campaign_id == campaign.id
        assert placement.slot_id == slot.id
        assert placement.assigned_by_user_id == "admin-1"

    def test_draft_campaign_cannot_be_placed(self):
        campaign = ContentCampaign.create(name="Campaña", content_id=new_uuid())
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_pending_approval_campaign_cannot_be_placed(self):
        campaign = ContentCampaign.create(name="Campaña", content_id=new_uuid())
        campaign.submit_for_approval()
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_approved_but_not_yet_activated_campaign_cannot_be_placed(self):
        campaign = ContentCampaign.create(name="Campaña", content_id=new_uuid())
        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="admin-1")
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_deactivated_campaign_cannot_be_placed(self):
        campaign = _active_campaign()
        campaign.deactivate()
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_expired_campaign_cannot_be_placed(self):
        campaign = _active_campaign()
        campaign.expire()
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_archived_campaign_cannot_be_placed(self):
        campaign = _active_campaign()
        campaign.expire()
        campaign.archive()
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, _slot())

    def test_inactive_slot_cannot_receive_a_placement(self):
        campaign = _active_campaign()
        slot = _slot()
        slot.deactivate()
        with pytest.raises(CampaignPlacementNotAllowedError):
            assign_placement(campaign, slot)
