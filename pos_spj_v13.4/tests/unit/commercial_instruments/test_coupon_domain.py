"""LOY-12 — CouponDefinition / CouponInstance / CouponRedemption (master
prompt §21)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.commercial_instruments.entities.coupon_definition import CouponDefinition
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.coupon_redemption import CouponRedemption
from backend.domain.commercial_instruments.enums import (
    CommercialBenefitType,
    CouponInstanceStatus,
    CouponType,
)
from backend.domain.commercial_instruments.exceptions import (
    InvalidCouponDefinitionError,
    InvalidCouponInstanceStateError,
)
from backend.shared.ids import new_uuid


class TestCouponDefinition:
    def test_create_defaults(self):
        definition = CouponDefinition.create(
            "WELCOME10", "10% de bienvenida", CouponType.PUBLIC_CODE,
            CommercialBenefitType.PERCENTAGE, Decimal("10"))
        assert definition.active is True
        assert definition.max_redemptions_per_instance == 1

    def test_rejects_non_positive_benefit_value(self):
        with pytest.raises(InvalidCouponDefinitionError):
            CouponDefinition.create(
                "X", "X", CouponType.PUBLIC_CODE, CommercialBenefitType.PERCENTAGE,
                Decimal("0"))

    def test_rejects_float_benefit_value(self):
        with pytest.raises(InvalidCouponDefinitionError):
            CouponDefinition.create(
                "X", "X", CouponType.PUBLIC_CODE, CommercialBenefitType.PERCENTAGE, 10.0)

    def test_activate_deactivate(self):
        definition = CouponDefinition.create(
            "X", "X", CouponType.AUTOMATIC, CommercialBenefitType.FIXED_AMOUNT,
            Decimal("50"))
        definition.deactivate()
        assert definition.active is False
        definition.activate()
        assert definition.active is True


class TestCouponInstance:
    def test_issue_defaults_to_active(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        assert instance.status is CouponInstanceStatus.ACTIVE
        assert instance.is_usable() is True

    def test_reserve_confirm_flow(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        sale_id = new_uuid()
        instance.reserve(sale_id)
        assert instance.status is CouponInstanceStatus.RESERVED
        instance.confirm_redemption()
        assert instance.status is CouponInstanceStatus.REDEEMED
        assert instance.redeemed_at is not None

    def test_release_restores_active(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        instance.reserve(new_uuid())
        instance.release()
        assert instance.status is CouponInstanceStatus.ACTIVE
        assert instance.sale_id is None

    def test_cannot_confirm_without_reserving(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        with pytest.raises(InvalidCouponInstanceStateError):
            instance.confirm_redemption()

    def test_cannot_reserve_a_redeemed_coupon(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        instance.reserve(new_uuid())
        instance.confirm_redemption()
        with pytest.raises(InvalidCouponInstanceStateError):
            instance.reserve(new_uuid())

    def test_cancel_requires_reason(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        with pytest.raises(InvalidCouponInstanceStateError):
            instance.cancel("")

    def test_block_and_cannot_reserve_blocked(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        instance.block("Código comprometido")
        assert instance.status is CouponInstanceStatus.BLOCKED
        with pytest.raises(InvalidCouponInstanceStateError):
            instance.reserve(new_uuid())

    def test_expire(self):
        instance = CouponInstance.issue(new_uuid(), "ABC123")
        instance.expire()
        assert instance.status is CouponInstanceStatus.EXPIRED


class TestCouponRedemption:
    def test_record(self):
        redemption = CouponRedemption.record(
            new_uuid(), new_uuid(), Decimal("25.00"), new_uuid())
        assert redemption.amount_applied == Decimal("25.00")

    def test_rejects_float_amount(self):
        with pytest.raises(InvalidCouponInstanceStateError):
            CouponRedemption.record(new_uuid(), new_uuid(), 25.0, new_uuid())
