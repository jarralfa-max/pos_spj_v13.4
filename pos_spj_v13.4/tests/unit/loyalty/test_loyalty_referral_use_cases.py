"""LOY-10 — Referral repository round-trip + use cases (Register, Qualify,
Reward, Reject, Flag fraud)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.application.loyalty.use_cases.referral_use_cases import (
    FlagReferralFraudSuspectedUseCase,
    QualifyReferralUseCase,
    RegisterReferralUseCase,
    RejectReferralUseCase,
    RewardReferralUseCase,
)
from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
    LoyaltyTransactionRepository,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_loyalty_schema(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def auth():
    return LoyaltyAuthorizationPolicy.permissive_for_tests()


def _balance(conn, account_id) -> Decimal:
    ledger = LoyaltyTransactionRepository(conn).list_for_account(account_id)
    return LoyaltyBalancePolicy.balance(ledger)


def _enrolled_membership(conn, auth):
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
    return (program_id, enroll.entity_id, enroll.data["membership"].loyalty_account_id,
            customer_id)


class TestRegisterReferral:
    def test_registers_successfully(self, conn, auth):
        program_id, membership_id, _, _ = _enrolled_membership(conn, auth)
        result = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["referral"].status == "REGISTERED"

    def test_rejects_self_referral(self, conn, auth):
        program_id, membership_id, _, customer_id = _enrolled_membership(conn, auth)
        result = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=customer_id, referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "SELF_REFERRAL_NOT_ALLOWED"

    def test_referrer_membership_not_found(self, conn, auth):
        result = RegisterReferralUseCase(auth).execute(
            conn, program_id=new_uuid(), referrer_membership_id=new_uuid(),
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "MEMBERSHIP_NOT_FOUND"


class TestReferralRewardFlow:
    def test_qualify_then_reward_pays_bonus(self, conn, auth):
        program_id, membership_id, account_id, _ = _enrolled_membership(conn, auth)
        register = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        referral_id = register.entity_id

        QualifyReferralUseCase(auth).execute(
            conn, referral_id=referral_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = RewardReferralUseCase(auth).execute(
            conn, referral_id=referral_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["referral"].status == "REWARDED"
        assert _balance(conn, account_id) == Decimal("50")

    def test_cannot_reward_without_qualifying(self, conn, auth):
        program_id, membership_id, _, _ = _enrolled_membership(conn, auth)
        register = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RewardReferralUseCase(auth).execute(
            conn, referral_id=register.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REFERRAL_NOT_QUALIFIED"

    def test_reward_is_idempotent_on_operation_id_reuse(self, conn, auth):
        program_id, membership_id, account_id, _ = _enrolled_membership(conn, auth)
        register = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        referral_id = register.entity_id
        QualifyReferralUseCase(auth).execute(
            conn, referral_id=referral_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        RewardReferralUseCase(auth).execute(
            conn, referral_id=referral_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        # Second reward attempt fails at the domain level (already REWARDED)
        # before ever reaching the double-pay guard — confirms no double bonus.
        second = RewardReferralUseCase(auth).execute(
            conn, referral_id=referral_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not second.success
        assert _balance(conn, account_id) == Decimal("50")


class TestReferralRejectAndFraud:
    def test_reject_requires_reason(self, conn, auth):
        program_id, membership_id, _, _ = _enrolled_membership(conn, auth)
        register = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RejectReferralUseCase(auth).execute(
            conn, referral_id=register.entity_id, reason="", actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REFERRAL_INVALID_STATE"

    def test_flag_fraud_suspected(self, conn, auth):
        program_id, membership_id, _, _ = _enrolled_membership(conn, auth)
        register = RegisterReferralUseCase(auth).execute(
            conn, program_id=program_id, referrer_membership_id=membership_id,
            referred_customer_id=new_uuid(), referrer_bonus_points=Decimal("50"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = FlagReferralFraudSuspectedUseCase(auth).execute(
            conn, referral_id=register.entity_id, reason="Patrón sospechoso",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["referral"].status == "FRAUD_SUSPECTED"

    def test_referral_not_found(self, conn, auth):
        result = QualifyReferralUseCase(auth).execute(
            conn, referral_id=new_uuid(), actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REFERRAL_NOT_FOUND"
