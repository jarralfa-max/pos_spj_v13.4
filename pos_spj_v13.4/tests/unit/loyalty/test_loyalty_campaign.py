"""LOY-11 — Campaign entity (master prompt §19, §60)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.campaign import Campaign
from backend.domain.loyalty.enums import CampaignStatus, CampaignType
from backend.domain.loyalty.exceptions import (
    InvalidCampaignStateError,
    LoyaltySegregationOfDutiesError,
)
from backend.shared.ids import new_uuid


def _campaign(**overrides) -> Campaign:
    defaults = dict(
        program_id=new_uuid(), code="SUMMER26", name="Verano 2026",
        campaign_type=CampaignType.SEASONAL, created_by_user_id=new_uuid())
    defaults.update(overrides)
    return Campaign.create(**defaults)


class TestCampaignCreation:
    def test_defaults_to_draft(self):
        campaign = _campaign()
        assert campaign.status is CampaignStatus.DRAFT

    def test_rejects_negative_budget(self):
        with pytest.raises(InvalidCampaignStateError):
            _campaign(budget_limit=Decimal("-100"))

    def test_rejects_float_budget(self):
        with pytest.raises(InvalidCampaignStateError):
            _campaign(budget_limit=100.0)


class TestCampaignLifecycle:
    def test_full_flow_with_distinct_users(self):
        creator = new_uuid()
        approver = new_uuid()
        campaign = _campaign(created_by_user_id=creator)
        campaign.submit_for_approval()
        campaign.approve(approver)
        assert campaign.status is CampaignStatus.APPROVED
        campaign.schedule()
        campaign.activate(approver)
        assert campaign.is_active()
        campaign.pause()
        campaign.activate(approver)
        campaign.complete()
        assert campaign.status is CampaignStatus.COMPLETED

    def test_creator_cannot_approve_own_campaign(self):
        creator = new_uuid()
        campaign = _campaign(created_by_user_id=creator)
        campaign.submit_for_approval()
        with pytest.raises(LoyaltySegregationOfDutiesError):
            campaign.approve(creator)

    def test_creator_cannot_activate_alone(self):
        creator = new_uuid()
        campaign = _campaign(created_by_user_id=creator)
        campaign.submit_for_approval()
        campaign.approve(new_uuid())
        campaign.schedule()
        with pytest.raises(LoyaltySegregationOfDutiesError):
            campaign.activate(creator)

    def test_cancel_requires_reason(self):
        campaign = _campaign()
        with pytest.raises(InvalidCampaignStateError):
            campaign.cancel("")

    def test_cannot_cancel_completed_campaign(self):
        creator = new_uuid()
        approver = new_uuid()
        campaign = _campaign(created_by_user_id=creator)
        campaign.submit_for_approval()
        campaign.approve(approver)
        campaign.schedule()
        campaign.activate(approver)
        campaign.complete()
        with pytest.raises(InvalidCampaignStateError):
            campaign.cancel("motivo")
