"""LOY-2 — LoyaltyMembership lifecycle (master prompt §10)."""

from __future__ import annotations

import pytest

from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.enums import MembershipStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyMembershipStateError
from backend.shared.ids import new_uuid


class TestLoyaltyMembership:
    def test_enroll_defaults_to_active(self):
        membership = LoyaltyMembership.enroll(new_uuid(), new_uuid())
        assert membership.status is MembershipStatus.ACTIVE
        assert membership.current_tier_id is None

    def test_requires_account_and_program(self):
        with pytest.raises(InvalidLoyaltyMembershipStateError):
            LoyaltyMembership.enroll("", new_uuid())
        with pytest.raises(InvalidLoyaltyMembershipStateError):
            LoyaltyMembership.enroll(new_uuid(), "")

    def test_suspend_block_reactivate(self):
        membership = LoyaltyMembership.enroll(new_uuid(), new_uuid())
        membership.suspend("Revisión")
        assert membership.status is MembershipStatus.SUSPENDED
        membership.reactivate()
        assert membership.status is MembershipStatus.ACTIVE
        membership.block("Fraude confirmado")
        assert membership.status is MembershipStatus.BLOCKED
        membership.reactivate()
        assert membership.status is MembershipStatus.ACTIVE

    def test_cannot_block_a_closed_membership(self):
        membership = LoyaltyMembership.enroll(new_uuid(), new_uuid())
        membership.close("Cliente cerró cuenta")
        with pytest.raises(InvalidLoyaltyMembershipStateError):
            membership.block("motivo")

    def test_change_tier(self):
        membership = LoyaltyMembership.enroll(new_uuid(), new_uuid())
        tier_id = new_uuid()
        membership.change_tier(tier_id)
        assert membership.current_tier_id == tier_id
