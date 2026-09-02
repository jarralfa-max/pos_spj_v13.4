"""LOY-8 — Reward repository round-trip + use cases (Create, Request,
Confirm, Cancel)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.ledger_use_cases import AccrueLoyaltyPointsUseCase
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.application.loyalty.use_cases.reward_use_cases import (
    CancelRewardRedemptionUseCase,
    ConfirmRewardRedemptionUseCase,
    CreateRewardUseCase,
    RequestRewardRedemptionUseCase,
)
from backend.domain.loyalty.enums import RewardType
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


def _enrolled_membership_with_points(conn, auth, points: str):
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

    enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=new_uuid(), program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    membership_id = enroll.entity_id
    loyalty_account_id = enroll.data["membership"].loyalty_account_id

    AccrueLoyaltyPointsUseCase(auth).execute(
        conn, loyalty_account_id=loyalty_account_id, points_amount=Decimal(points),
        operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        source_module="sales")
    return program_id, membership_id, loyalty_account_id


class TestCreateReward:
    def test_creates_reward(self, conn, auth):
        create = CreateLoyaltyProgramUseCase(auth).execute(
            conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = CreateRewardUseCase(auth).execute(
            conn, program_id=create.entity_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("100"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["reward"].points_cost == Decimal("100")

    def test_program_not_found(self, conn, auth):
        result = CreateRewardUseCase(auth).execute(
            conn, program_id=new_uuid(), code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("100"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PROGRAM_NOT_FOUND"


class TestRedemptionFlow:
    def test_request_reserves_points(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership_with_points(
            conn, auth, "100")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        result = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["redemption"].status == "RESERVED"
        assert _balance(conn, account_id) == Decimal("60")

    def test_request_rejects_insufficient_points(self, conn, auth):
        program_id, membership_id, _ = _enrolled_membership_with_points(conn, auth, "10")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "INSUFFICIENT_POINTS"

    def test_request_rejects_inactive_reward(self, conn, auth):
        from backend.infrastructure.db.repositories.loyalty.reward_repository import (
            RewardRepository,
        )

        program_id, membership_id, _ = _enrolled_membership_with_points(conn, auth, "100")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        repo = RewardRepository(conn)
        entity = repo.get(reward.entity_id)
        entity.deactivate()
        repo.save(entity)

        result = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWARD_NOT_AVAILABLE"

    def test_confirm_does_not_change_balance_further(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership_with_points(
            conn, auth, "100")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        request = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        balance_after_request = _balance(conn, account_id)

        confirm = ConfirmRewardRedemptionUseCase(auth).execute(
            conn, redemption_id=request.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert confirm.success
        assert confirm.data["redemption"].status == "CONFIRMED"
        assert _balance(conn, account_id) == balance_after_request

    def test_cancel_restores_balance(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership_with_points(
            conn, auth, "100")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        request = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())

        cancel = CancelRewardRedemptionUseCase(auth).execute(
            conn, redemption_id=request.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert cancel.success
        assert cancel.data["redemption"].status == "CANCELLED"
        assert _balance(conn, account_id) == Decimal("100")

    def test_cannot_confirm_a_cancelled_redemption(self, conn, auth):
        program_id, membership_id, _ = _enrolled_membership_with_points(conn, auth, "100")
        reward = CreateRewardUseCase(auth).execute(
            conn, program_id=program_id, code="COFFEE", name="Café gratis",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("40"),
            actor_user_id=new_uuid(), operation_id=new_uuid())
        request = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward.entity_id, membership_id=membership_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        CancelRewardRedemptionUseCase(auth).execute(
            conn, redemption_id=request.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())

        result = ConfirmRewardRedemptionUseCase(auth).execute(
            conn, redemption_id=request.entity_id, actor_user_id=new_uuid(),
            actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWARD_REDEMPTION_INVALID_STATE"

    def test_redemption_across_programs_rejected(self, conn, auth):
        program_a, membership_a, _ = _enrolled_membership_with_points(conn, auth, "100")
        create_b = CreateLoyaltyProgramUseCase(auth).execute(
            conn, code="VIP", name="VIP", currency_name="Puntos",
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        reward_b = CreateRewardUseCase(auth).execute(
            conn, program_id=create_b.entity_id, code="X", name="X",
            reward_type=RewardType.PRODUCT, points_cost=Decimal("10"),
            actor_user_id=new_uuid(), operation_id=new_uuid())

        result = RequestRewardRedemptionUseCase(auth).execute(
            conn, reward_id=reward_b.entity_id, membership_id=membership_a,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "REWARD_NOT_AVAILABLE"
