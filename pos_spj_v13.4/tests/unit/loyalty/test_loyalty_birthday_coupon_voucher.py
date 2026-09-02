"""LOY-24 — birthday COUPON/VOUCHER benefit types (closing LOY-14's own
flagged gap, master prompt §18)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.birthday_use_cases import (
    ConfigureBirthdayBenefitUseCase,
    GrantBirthdayBenefitUseCase,
)
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.domain.commercial_instruments.entities.coupon_definition import CouponDefinition
from backend.domain.commercial_instruments.entities.voucher_definition import VoucherDefinition
from backend.domain.commercial_instruments.enums import (
    CommercialBenefitType,
    CouponType,
    VoucherType,
)
from backend.domain.loyalty.enums import BirthdayBenefitType
from backend.infrastructure.db.repositories.commercial_instruments.coupon_repository import (
    CouponDefinitionRepository,
    CouponInstanceRepository,
)
from backend.infrastructure.db.repositories.commercial_instruments.voucher_repository import (
    VoucherDefinitionRepository,
    VoucherInstanceRepository,
)
from backend.infrastructure.db.schema.commercial_instruments_schema import (
    create_commercial_instruments_schema,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_schema(c)
    create_commercial_instruments_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def _active_program_and_membership(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    program_id = create.entity_id
    customer_id = new_uuid()
    enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return program_id, enroll.data["membership"].loyalty_account_id, customer_id


def _coupon_definition(conn) -> str:
    definition = CouponDefinition.create(
        "BDAYCOUPON", "Cupón de cumpleaños", CouponType.BIRTHDAY,
        CommercialBenefitType.PERCENTAGE, Decimal("10"))
    CouponDefinitionRepository(conn).save(definition)
    return definition.id


def _voucher_definition(conn) -> str:
    definition = VoucherDefinition.create("BDAYVOUCHER", "Vale de cumpleaños",
                                          VoucherType.PROMOTIONAL_VOUCHER)
    VoucherDefinitionRepository(conn).save(definition)
    return definition.id


class TestGrantBirthdayCoupon:
    def test_grants_coupon_with_consent(self, conn, auth):
        program_id, account_id, customer_id = _active_program_and_membership(conn, auth)
        coupon_definition_id = _coupon_definition(conn)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.COUPON, coupon_definition_id=coupon_definition_id)

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is True
        assert result.data["coupon_code"]

        instance = CouponInstanceRepository(conn).get(result.entity_id)
        assert instance is not None
        assert instance.definition_id == coupon_definition_id
        assert instance.customer_id == customer_id
        assert instance.status.value == "ACTIVE"

    def test_coupon_definition_not_found_fails_closed(self, conn, auth):
        program_id, account_id, _customer_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.COUPON, coupon_definition_id=new_uuid())

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "COUPON_DEFINITION_NOT_FOUND"

    def test_denies_without_consent(self, conn, auth):
        program_id, account_id, _customer_id = _active_program_and_membership(conn, auth)
        coupon_definition_id = _coupon_definition(conn)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.COUPON, coupon_definition_id=coupon_definition_id)

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=False, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CONSENT_REQUIRED"


class TestGrantBirthdayVoucher:
    def test_grants_voucher_with_consent(self, conn, auth):
        program_id, account_id, customer_id = _active_program_and_membership(conn, auth)
        voucher_definition_id = _voucher_definition(conn)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.VOUCHER, voucher_definition_id=voucher_definition_id,
            points_amount=Decimal("200"))

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["granted"] is True
        assert result.data["voucher_code"]

        instance = VoucherInstanceRepository(conn).get(result.entity_id)
        assert instance is not None
        assert instance.definition_id == voucher_definition_id
        assert instance.customer_id == customer_id

    def test_voucher_definition_not_found_fails_closed(self, conn, auth):
        program_id, account_id, _customer_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.VOUCHER, voucher_definition_id=new_uuid(),
            points_amount=Decimal("200"))

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "VOUCHER_DEFINITION_NOT_FOUND"


class TestGrantBirthdayReward:
    def test_reward_still_not_implemented(self, conn, auth):
        program_id, account_id, _customer_id = _active_program_and_membership(conn, auth)
        ConfigureBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, actor_user_id=new_uuid(), operation_id=new_uuid(),
            benefit_type=BirthdayBenefitType.REWARD, reward_id=new_uuid())

        result = GrantBirthdayBenefitUseCase(auth).execute(
            conn, program_id=program_id, loyalty_account_id=account_id,
            has_marketing_consent=True, actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "NOT_IMPLEMENTED"
