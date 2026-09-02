"""LOY-9 — Gamification repositories + use cases (Create/Activate challenge,
Record progress, Record streak)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.gamification_use_cases import (
    ActivateLoyaltyChallengeUseCase,
    CreateLoyaltyChallengeUseCase,
    RecordChallengeProgressUseCase,
    RecordLoyaltyStreakActivityUseCase,
)
from backend.application.loyalty.use_cases.membership_use_cases import (
    EnrollLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
)
from backend.domain.loyalty.enums import ChallengeCriteriaType
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

    enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=new_uuid(), program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    return program_id, enroll.entity_id, enroll.data["membership"].loyalty_account_id


def _active_challenge(conn, auth, program_id, target="5", reward="100"):
    create = CreateLoyaltyChallengeUseCase(auth).execute(
        conn, program_id=program_id, code="5_PURCHASES", name="5 compras",
        criteria_type=ChallengeCriteriaType.PURCHASE_COUNT, target_value=Decimal(target),
        points_reward=Decimal(reward), actor_user_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyChallengeUseCase(auth).execute(
        conn, challenge_id=create.entity_id, actor_user_id=new_uuid(),
        operation_id=new_uuid())
    return create.entity_id


class TestCreateActivateChallenge:
    def test_create_and_activate(self, conn, auth):
        program_id, _, _ = _enrolled_membership(conn, auth)
        challenge_id = _active_challenge(conn, auth, program_id)
        assert challenge_id

    def test_program_not_found(self, conn, auth):
        result = CreateLoyaltyChallengeUseCase(auth).execute(
            conn, program_id=new_uuid(), code="X", name="X",
            criteria_type=ChallengeCriteriaType.PURCHASE_COUNT, target_value=Decimal("5"),
            points_reward=Decimal("100"), actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PROGRAM_NOT_FOUND"


class TestRecordChallengeProgress:
    def test_partial_progress_does_not_complete(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership(conn, auth)
        challenge_id = _active_challenge(conn, auth, program_id, target="5", reward="100")

        result = RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=challenge_id, membership_id=membership_id,
            amount=Decimal("3"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["completed"] is False
        assert _balance(conn, account_id) == Decimal("0")

    def test_reaching_target_grants_points_and_badge(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership(conn, auth)
        challenge_id = _active_challenge(conn, auth, program_id, target="5", reward="100")

        RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=challenge_id, membership_id=membership_id,
            amount=Decimal("3"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=challenge_id, membership_id=membership_id,
            amount=Decimal("2"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert result.data["completed"] is True
        assert _balance(conn, account_id) == Decimal("100")

        badges = conn.execute(
            "SELECT COUNT(*) FROM loyalty_badges WHERE membership_id=?",
            (membership_id,)).fetchone()
        assert badges[0] == 1

    def test_further_progress_after_completion_does_not_double_pay(self, conn, auth):
        program_id, membership_id, account_id = _enrolled_membership(conn, auth)
        challenge_id = _active_challenge(conn, auth, program_id, target="2", reward="100")

        RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=challenge_id, membership_id=membership_id,
            amount=Decimal("2"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=challenge_id, membership_id=membership_id,
            amount=Decimal("1"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "CHALLENGE_PROGRESS_INVALID"
        assert _balance(conn, account_id) == Decimal("100")

    def test_inactive_challenge_rejected(self, conn, auth):
        program_id, membership_id, _ = _enrolled_membership(conn, auth)
        create = CreateLoyaltyChallengeUseCase(auth).execute(
            conn, program_id=program_id, code="X", name="X",
            criteria_type=ChallengeCriteriaType.PURCHASE_COUNT, target_value=Decimal("5"),
            points_reward=Decimal("100"), actor_user_id=new_uuid(), operation_id=new_uuid())
        result = RecordChallengeProgressUseCase(auth).execute(
            conn, challenge_id=create.entity_id, membership_id=membership_id,
            amount=Decimal("1"), actor_branch_id=new_uuid(), operation_id=new_uuid())
        assert not result.success


class TestRecordStreakActivity:
    def test_creates_and_updates_streak(self, conn, auth):
        _, membership_id, _ = _enrolled_membership(conn, auth)
        RecordLoyaltyStreakActivityUseCase(auth).execute(
            conn, membership_id=membership_id, streak_type="WEEKLY_PURCHASE",
            period="2026-W01", is_consecutive=True)
        result = RecordLoyaltyStreakActivityUseCase(auth).execute(
            conn, membership_id=membership_id, streak_type="WEEKLY_PURCHASE",
            period="2026-W02", is_consecutive=True)
        assert result.success
        assert result.data["current_count"] == 2
