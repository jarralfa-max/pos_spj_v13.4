"""LOY-8 — Reward / RewardRedemption entities (master prompt §15)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.reward import Reward
from backend.domain.loyalty.entities.reward_redemption import RewardRedemption
from backend.domain.loyalty.enums import RewardRedemptionStatus, RewardType
from backend.domain.loyalty.exceptions import (
    InvalidRewardError,
    InvalidRewardRedemptionStateError,
)
from backend.shared.ids import new_uuid


class TestReward:
    def test_create_defaults(self):
        reward = Reward.create(new_uuid(), "FREE_COFFEE", "Café gratis",
                                RewardType.PRODUCT, Decimal("100"))
        assert reward.active is True
        assert reward.value == Decimal("0")

    def test_requires_positive_points_cost(self):
        with pytest.raises(InvalidRewardError):
            Reward.create(new_uuid(), "X", "X", RewardType.PRODUCT, Decimal("0"))
        with pytest.raises(InvalidRewardError):
            Reward.create(new_uuid(), "X", "X", RewardType.PRODUCT, Decimal("-10"))

    def test_rejects_float_points_cost(self):
        with pytest.raises(InvalidRewardError):
            Reward.create(new_uuid(), "X", "X", RewardType.PRODUCT, 100.0)

    def test_activate_deactivate(self):
        reward = Reward.create(new_uuid(), "X", "X", RewardType.DISCOUNT, Decimal("50"))
        reward.deactivate()
        assert reward.active is False
        reward.activate()
        assert reward.active is True


class TestRewardRedemption:
    def test_request_defaults_to_reserved(self):
        redemption = RewardRedemption.request(
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        assert redemption.status is RewardRedemptionStatus.RESERVED

    def test_confirm(self):
        redemption = RewardRedemption.request(
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        redemption.confirm()
        assert redemption.status is RewardRedemptionStatus.CONFIRMED
        assert redemption.confirmed_at is not None

    def test_cancel(self):
        redemption = RewardRedemption.request(
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        redemption.cancel()
        assert redemption.status is RewardRedemptionStatus.CANCELLED

    def test_cannot_confirm_twice(self):
        redemption = RewardRedemption.request(
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        redemption.confirm()
        with pytest.raises(InvalidRewardRedemptionStateError):
            redemption.confirm()

    def test_cannot_cancel_a_confirmed_redemption(self):
        redemption = RewardRedemption.request(
            new_uuid(), new_uuid(), new_uuid(), new_uuid())
        redemption.confirm()
        with pytest.raises(InvalidRewardRedemptionStateError):
            redemption.cancel()
