"""LOY-10 — Referral entity (master prompt §17)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.referral import Referral
from backend.domain.loyalty.enums import ReferralStatus
from backend.domain.loyalty.exceptions import (
    InvalidReferralStateError,
    ReferralNotQualifiedError,
)
from backend.shared.ids import new_uuid


def _referral(**overrides) -> Referral:
    defaults = dict(
        program_id=new_uuid(), referrer_membership_id=new_uuid(),
        referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("100"))
    defaults.update(overrides)
    return Referral.register(**defaults)


class TestReferralCreation:
    def test_register_defaults(self):
        referral = _referral()
        assert referral.status is ReferralStatus.REGISTERED
        assert referral.referred_bonus_points == Decimal("0")

    def test_rejects_negative_bonus(self):
        with pytest.raises(InvalidReferralStateError):
            _referral(referrer_bonus_points=Decimal("-1"))

    def test_rejects_float_bonus(self):
        with pytest.raises(InvalidReferralStateError):
            _referral(referrer_bonus_points=100.0)


class TestReferralLifecycle:
    def test_full_flow(self):
        referral = _referral()
        referral.qualify()
        assert referral.status is ReferralStatus.QUALIFIED
        referral.reward()
        assert referral.status is ReferralStatus.REWARDED
        assert referral.rewarded_at is not None

    def test_cannot_reward_before_qualifying(self):
        referral = _referral()
        with pytest.raises(ReferralNotQualifiedError):
            referral.reward()

    def test_reject_requires_reason(self):
        referral = _referral()
        with pytest.raises(InvalidReferralStateError):
            referral.reject("")

    def test_cannot_reject_after_reward(self):
        referral = _referral()
        referral.qualify()
        referral.reward()
        with pytest.raises(InvalidReferralStateError):
            referral.reject("motivo")

    def test_expire(self):
        referral = _referral()
        referral.expire()
        assert referral.status is ReferralStatus.EXPIRED

    def test_flag_fraud_suspected(self):
        referral = _referral()
        referral.flag_fraud_suspected("Auto-referido detectado")
        assert referral.status is ReferralStatus.FRAUD_SUSPECTED

    def test_cannot_flag_fraud_after_reward(self):
        referral = _referral()
        referral.qualify()
        referral.reward()
        with pytest.raises(InvalidReferralStateError):
            referral.flag_fraud_suspected("motivo")
