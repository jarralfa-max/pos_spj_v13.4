"""SET-18 — "Campaigns"/"Approval": ContentCampaign state machine. Pure
domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.customer_display.entities.content_campaign import ContentCampaign
from backend.domain.customer_display.enums import ContentCampaignStatus
from backend.domain.customer_display.exceptions import (
    ContentCampaignApprovalSegregationError,
    ContentCampaignTransitionNotAllowedError,
    CustomerDisplayInvalidValueError,
)
from backend.shared.ids import is_uuidv7, new_uuid


def _campaign(**overrides) -> ContentCampaign:
    kwargs = dict(name="Campaña Verano", content_id=new_uuid())
    kwargs.update(overrides)
    return ContentCampaign.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_starts_at_draft(self):
        campaign = _campaign()
        assert is_uuidv7(campaign.id)
        assert campaign.status is ContentCampaignStatus.DRAFT

    def test_requires_name(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _campaign(name="   ")

    def test_validates_content_id_as_uuid(self):
        with pytest.raises(ValueError):
            _campaign(content_id="not-a-uuid")

    def test_rejects_ends_at_before_starts_at(self):
        with pytest.raises(CustomerDisplayInvalidValueError):
            _campaign(starts_at="2026-09-01", ends_at="2026-08-01")

    def test_accepts_valid_period(self):
        campaign = _campaign(starts_at="2026-08-01", ends_at="2026-09-01")
        assert campaign.starts_at == "2026-08-01"
        assert campaign.ends_at == "2026-09-01"


class TestLifecycle:
    def test_full_happy_path(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        assert campaign.status is ContentCampaignStatus.PENDING_APPROVAL

        campaign.approve(approved_by_user_id="admin-1")
        assert campaign.status is ContentCampaignStatus.APPROVED
        assert campaign.approved_by_user_id == "admin-1"

        campaign.activate(activated_by_user_id="admin-1")
        assert campaign.status is ContentCampaignStatus.ACTIVE
        assert campaign.is_active() is True

        campaign.deactivate()
        assert campaign.status is ContentCampaignStatus.INACTIVE
        assert campaign.is_active() is False

        campaign.archive()
        assert campaign.status is ContentCampaignStatus.ARCHIVED

    def test_active_can_expire_then_archive(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="admin-1")
        campaign.activate(activated_by_user_id="admin-1")
        campaign.expire()
        assert campaign.status is ContentCampaignStatus.EXPIRED
        campaign.archive()
        assert campaign.status is ContentCampaignStatus.ARCHIVED

    def test_reject_returns_to_draft_and_can_be_resubmitted(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        campaign.reject(reason="Contenido inapropiado")
        assert campaign.status is ContentCampaignStatus.DRAFT
        assert campaign.reason == "Contenido inapropiado"
        campaign.submit_for_approval()
        assert campaign.status is ContentCampaignStatus.PENDING_APPROVAL

    def test_reject_requires_reason(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        with pytest.raises(CustomerDisplayInvalidValueError):
            campaign.reject(reason="   ")

    def test_approve_requires_approved_by_user_id(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        with pytest.raises(CustomerDisplayInvalidValueError):
            campaign.approve(approved_by_user_id="")

    def test_activate_requires_activated_by_user_id(self):
        campaign = _campaign()
        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="admin-1")
        with pytest.raises(CustomerDisplayInvalidValueError):
            campaign.activate(activated_by_user_id="")

    @pytest.mark.parametrize(
        "method,kwargs",
        [
            ("approve", {"approved_by_user_id": "admin-1"}),
            ("reject", {"reason": "x"}),
            ("activate", {"activated_by_user_id": "admin-1"}),
            ("deactivate", {}),
            ("expire", {}),
            ("archive", {}),
        ],
    )
    def test_transitions_not_allowed_from_fresh_draft(self, method, kwargs):
        campaign = _campaign()
        with pytest.raises(ContentCampaignTransitionNotAllowedError):
            getattr(campaign, method)(**kwargs)


class TestApprovalSegregation:
    """SET-18 repegado: the same §59 segregation-of-duties rule the SET-1
    round added to `DocumentTemplateVersion.approve()` — mirrored here
    since this entity's own docstring already claims that shape."""

    def test_creator_cannot_approve_own_campaign(self):
        campaign = _campaign(created_by_user_id="user-1")
        campaign.submit_for_approval()
        with pytest.raises(ContentCampaignApprovalSegregationError):
            campaign.approve(approved_by_user_id="user-1")

    def test_a_different_approver_succeeds(self):
        campaign = _campaign(created_by_user_id="user-1")
        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="user-2")
        assert campaign.status is ContentCampaignStatus.APPROVED

    def test_no_creator_recorded_never_blocks_approval(self):
        campaign = _campaign(created_by_user_id=None)
        campaign.submit_for_approval()
        campaign.approve(approved_by_user_id="user-2")
        assert campaign.status is ContentCampaignStatus.APPROVED


class TestUpdateSchedule:
    def test_sets_both_dates(self):
        campaign = _campaign()
        campaign.update_schedule(starts_at="2026-08-01", ends_at="2026-09-01")
        assert campaign.starts_at == "2026-08-01"
        assert campaign.ends_at == "2026-09-01"

    def test_clears_both_dates(self):
        campaign = _campaign(starts_at="2026-08-01", ends_at="2026-09-01")
        campaign.update_schedule(starts_at=None, ends_at=None)
        assert campaign.starts_at is None
        assert campaign.ends_at is None

    def test_rejects_ends_before_starts(self):
        campaign = _campaign()
        with pytest.raises(CustomerDisplayInvalidValueError):
            campaign.update_schedule(starts_at="2026-09-01", ends_at="2026-08-01")
