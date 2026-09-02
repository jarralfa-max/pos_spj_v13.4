"""LOY-7 — Tier repository round-trip + use cases (Create, Evaluate)."""

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
from backend.application.loyalty.use_cases.tier_use_cases import (
    CreateLoyaltyTierUseCase,
    EvaluateLoyaltyMembershipTierUseCase,
)
from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier
from backend.infrastructure.db.repositories.loyalty.program_repository import (
    LoyaltyProgramRepository,
)
from backend.infrastructure.db.repositories.loyalty.tier_repository import (
    LoyaltyTierRepository,
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


def _active_program(conn, auth) -> str:
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    return create.entity_id


def _saved_program_id(conn) -> str:
    program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
    LoyaltyProgramRepository(conn).save(program)
    return program.id


class TestLoyaltyTierRepository:
    def test_round_trip(self, conn):
        repo = LoyaltyTierRepository(conn)
        tier = LoyaltyTier.create(_saved_program_id(conn), "BRZ", "Bronce", 1,
                                   minimum_points=Decimal("0"))
        repo.save(tier)
        fetched = repo.get(tier.id)
        assert fetched.code == "BRZ"
        assert fetched.minimum_points == Decimal("0")

    def test_list_active_for_program_orders_by_rank(self, conn):
        program_id = _saved_program_id(conn)
        repo = LoyaltyTierRepository(conn)
        gold = LoyaltyTier.create(program_id, "GLD", "Oro", 3, minimum_points=Decimal("2000"))
        bronze = LoyaltyTier.create(program_id, "BRZ", "Bronce", 1, minimum_points=Decimal("0"))
        silver = LoyaltyTier.create(program_id, "SLV", "Plata", 2, minimum_points=Decimal("500"))
        repo.save(gold)
        repo.save(bronze)
        repo.save(silver)
        result = repo.list_active_for_program(program_id)
        assert [t.code for t in result] == ["BRZ", "SLV", "GLD"]

    def test_duplicate_rank_in_same_program_violates_unique_constraint(self, conn):
        program_id = _saved_program_id(conn)
        repo = LoyaltyTierRepository(conn)
        repo.save(LoyaltyTier.create(program_id, "BRZ", "Bronce", 1))
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(LoyaltyTier.create(program_id, "OTHER", "Otro", 1))


class TestCreateLoyaltyTierUseCase:
    def test_creates_tier(self, conn, auth):
        program_id = _active_program(conn, auth)
        result = CreateLoyaltyTierUseCase(auth).execute(
            conn, program_id=program_id, code="BRZ", name="Bronce", rank=1,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert result.success
        assert result.data["tier"].code == "BRZ"

    def test_program_not_found(self, conn, auth):
        result = CreateLoyaltyTierUseCase(auth).execute(
            conn, program_id=new_uuid(), code="BRZ", name="Bronce", rank=1,
            actor_user_id=new_uuid(), operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "PROGRAM_NOT_FOUND"


class TestEvaluateLoyaltyMembershipTierUseCase:
    def test_evaluates_and_records_history(self, conn, auth):
        program_id = _active_program(conn, auth)
        CreateLoyaltyTierUseCase(auth).execute(
            conn, program_id=program_id, code="BRZ", name="Bronce", rank=1,
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            minimum_points=Decimal("0"))
        CreateLoyaltyTierUseCase(auth).execute(
            conn, program_id=program_id, code="SLV", name="Plata", rank=2,
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            minimum_points=Decimal("500"))

        enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
            conn, customer_id=new_uuid(), program_id=program_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        membership_id = enroll.entity_id
        loyalty_account_id = enroll.data["membership"].loyalty_account_id

        AccrueLoyaltyPointsUseCase(auth).execute(
            conn, loyalty_account_id=loyalty_account_id, points_amount=Decimal("600"),
            operation_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
            source_module="sales")

        result = EvaluateLoyaltyMembershipTierUseCase(auth).execute(
            conn, membership_id=membership_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["tier"].code == "SLV"

        history = conn.execute(
            "SELECT COUNT(*) FROM loyalty_tier_history WHERE membership_id=?",
            (membership_id,)).fetchone()
        assert history[0] == 1

    def test_no_change_does_not_duplicate_history(self, conn, auth):
        program_id = _active_program(conn, auth)
        CreateLoyaltyTierUseCase(auth).execute(
            conn, program_id=program_id, code="BRZ", name="Bronce", rank=1,
            actor_user_id=new_uuid(), operation_id=new_uuid(), minimum_points=Decimal("0"))
        enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
            conn, customer_id=new_uuid(), program_id=program_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        membership_id = enroll.entity_id

        EvaluateLoyaltyMembershipTierUseCase(auth).execute(
            conn, membership_id=membership_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        EvaluateLoyaltyMembershipTierUseCase(auth).execute(
            conn, membership_id=membership_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid())

        history = conn.execute(
            "SELECT COUNT(*) FROM loyalty_tier_history WHERE membership_id=?",
            (membership_id,)).fetchone()
        assert history[0] == 1

    def test_membership_not_found(self, conn, auth):
        result = EvaluateLoyaltyMembershipTierUseCase(auth).execute(
            conn, membership_id=new_uuid(), actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert not result.success
        assert result.error_code == "MEMBERSHIP_NOT_FOUND"

    def test_no_tiers_configured(self, conn, auth):
        program_id = _active_program(conn, auth)
        enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
            conn, customer_id=new_uuid(), program_id=program_id,
            actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
        result = EvaluateLoyaltyMembershipTierUseCase(auth).execute(
            conn, membership_id=enroll.entity_id, actor_branch_id=new_uuid(),
            operation_id=new_uuid())
        assert result.success
        assert result.data["tier"] is None
