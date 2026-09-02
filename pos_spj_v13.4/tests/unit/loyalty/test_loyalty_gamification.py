"""LOY-9 — LoyaltyChallenge / ChallengeProgress / LoyaltyStreak /
LoyaltyBadge (master prompt §16)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.challenge_progress import ChallengeProgress
from backend.domain.loyalty.entities.loyalty_badge import LoyaltyBadge
from backend.domain.loyalty.entities.loyalty_challenge import LoyaltyChallenge
from backend.domain.loyalty.entities.loyalty_streak import LoyaltyStreak
from backend.domain.loyalty.enums import ChallengeCriteriaType, ChallengeStatus
from backend.domain.loyalty.exceptions import (
    InvalidChallengeProgressError,
    InvalidLoyaltyChallengeStateError,
)
from backend.shared.ids import new_uuid


def _challenge(**overrides) -> LoyaltyChallenge:
    defaults = dict(
        program_id=new_uuid(), code="5_PURCHASES", name="5 compras",
        criteria_type=ChallengeCriteriaType.PURCHASE_COUNT,
        target_value=Decimal("5"), points_reward=Decimal("100"))
    defaults.update(overrides)
    return LoyaltyChallenge.create(**defaults)


class TestLoyaltyChallenge:
    def test_create_defaults_to_draft(self):
        challenge = _challenge()
        assert challenge.status is ChallengeStatus.DRAFT

    def test_requires_positive_target_and_reward(self):
        with pytest.raises(InvalidLoyaltyChallengeStateError):
            _challenge(target_value=Decimal("0"))
        with pytest.raises(InvalidLoyaltyChallengeStateError):
            _challenge(points_reward=Decimal("-1"))

    def test_lifecycle(self):
        challenge = _challenge()
        challenge.activate()
        assert challenge.is_active()
        challenge.expire()
        assert challenge.status is ChallengeStatus.EXPIRED

    def test_cannot_activate_twice(self):
        challenge = _challenge()
        challenge.activate()
        with pytest.raises(InvalidLoyaltyChallengeStateError):
            challenge.activate()

    def test_cancel_requires_reason(self):
        challenge = _challenge()
        with pytest.raises(InvalidLoyaltyChallengeStateError):
            challenge.cancel("")


class TestChallengeProgress:
    def test_increment_and_completion(self):
        progress = ChallengeProgress.start(new_uuid(), new_uuid())
        progress.increment(Decimal("3"))
        assert progress.current_value == Decimal("3")
        assert not progress.has_reached(Decimal("5"))
        progress.increment(Decimal("2"))
        assert progress.has_reached(Decimal("5"))
        progress.mark_completed(Decimal("100"))
        assert progress.completed is True
        assert progress.points_awarded == Decimal("100")

    def test_cannot_increment_after_completion(self):
        progress = ChallengeProgress.start(new_uuid(), new_uuid())
        progress.mark_completed(Decimal("100"))
        with pytest.raises(InvalidChallengeProgressError):
            progress.increment(Decimal("1"))

    def test_rejects_negative_increment(self):
        progress = ChallengeProgress.start(new_uuid(), new_uuid())
        with pytest.raises(InvalidChallengeProgressError):
            progress.increment(Decimal("-1"))

    def test_cannot_complete_twice(self):
        progress = ChallengeProgress.start(new_uuid(), new_uuid())
        progress.mark_completed(Decimal("100"))
        with pytest.raises(InvalidChallengeProgressError):
            progress.mark_completed(Decimal("50"))


class TestLoyaltyStreak:
    def test_records_consecutive_periods(self):
        streak = LoyaltyStreak.start(new_uuid(), "WEEKLY_PURCHASE")
        streak.record_period("2026-W01", is_consecutive=True)
        streak.record_period("2026-W02", is_consecutive=True)
        assert streak.current_count == 2
        assert streak.longest_count == 2

    def test_breaks_on_non_consecutive(self):
        streak = LoyaltyStreak.start(new_uuid(), "WEEKLY_PURCHASE")
        streak.record_period("2026-W01", is_consecutive=True)
        streak.record_period("2026-W02", is_consecutive=True)
        streak.record_period("2026-W05", is_consecutive=False)
        assert streak.current_count == 1
        assert streak.longest_count == 2

    def test_recording_same_period_twice_is_idempotent(self):
        streak = LoyaltyStreak.start(new_uuid(), "WEEKLY_PURCHASE")
        streak.record_period("2026-W01", is_consecutive=True)
        streak.record_period("2026-W01", is_consecutive=True)
        assert streak.current_count == 1

    def test_reset(self):
        streak = LoyaltyStreak.start(new_uuid(), "WEEKLY_PURCHASE")
        streak.record_period("2026-W01", is_consecutive=True)
        streak.reset()
        assert streak.current_count == 0
        assert streak.last_period is None


class TestLoyaltyBadge:
    def test_award(self):
        badge = LoyaltyBadge.award(new_uuid(), "5_STAR_CUSTOMER", source_challenge_id=new_uuid())
        assert badge.badge_code == "5_STAR_CUSTOMER"

    def test_requires_badge_code(self):
        with pytest.raises(InvalidChallengeProgressError):
            LoyaltyBadge.award(new_uuid(), "")
