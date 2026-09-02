"""LOY-14 — BirthdayBenefitConfig (master prompt §18)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.birthday_benefit_config import BirthdayBenefitConfig
from backend.domain.loyalty.enums import BirthdayBenefitType
from backend.domain.loyalty.exceptions import InvalidBirthdayBenefitConfigError
from backend.shared.ids import new_uuid


class TestBirthdayBenefitConfig:
    def test_create_defaults_to_none_benefit(self):
        config = BirthdayBenefitConfig.create(new_uuid())
        assert config.benefit_type is BirthdayBenefitType.NONE
        assert config.enabled is True

    def test_points_benefit_requires_positive_amount(self):
        with pytest.raises(InvalidBirthdayBenefitConfigError):
            BirthdayBenefitConfig.create(
                new_uuid(), benefit_type=BirthdayBenefitType.POINTS,
                points_amount=Decimal("0"))

    def test_points_benefit_with_amount_succeeds(self):
        config = BirthdayBenefitConfig.create(
            new_uuid(), benefit_type=BirthdayBenefitType.POINTS,
            points_amount=Decimal("100"))
        assert config.points_amount == Decimal("100")

    def test_coupon_benefit_requires_definition_id(self):
        with pytest.raises(InvalidBirthdayBenefitConfigError):
            BirthdayBenefitConfig.create(new_uuid(), benefit_type=BirthdayBenefitType.COUPON)

    def test_voucher_benefit_requires_definition_id(self):
        with pytest.raises(InvalidBirthdayBenefitConfigError):
            BirthdayBenefitConfig.create(new_uuid(), benefit_type=BirthdayBenefitType.VOUCHER)

    def test_reward_benefit_requires_reward_id(self):
        with pytest.raises(InvalidBirthdayBenefitConfigError):
            BirthdayBenefitConfig.create(new_uuid(), benefit_type=BirthdayBenefitType.REWARD)

    def test_negative_day_windows_rejected(self):
        with pytest.raises(InvalidBirthdayBenefitConfigError):
            BirthdayBenefitConfig.create(new_uuid(), days_before=-1)

    def test_enable_disable(self):
        config = BirthdayBenefitConfig.create(new_uuid())
        config.disable()
        assert config.enabled is False
        config.enable()
        assert config.enabled is True
