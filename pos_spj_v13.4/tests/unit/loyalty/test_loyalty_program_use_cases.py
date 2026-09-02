"""LOY-4 — LoyaltyProgram use cases: Create, Approve, Activate, Suspend."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
    SuspendLoyaltyProgramUseCase,
)
from backend.infrastructure.db.repositories.loyalty.program_repository import (
    LoyaltyProgramRepository,
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


def test_create_program(conn, auth):
    uc = CreateLoyaltyProgramUseCase(auth)
    result = uc.execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert result.success
    # Create immediately submits for approval (DRAFT -> PENDING_APPROVAL) —
    # see CreateLoyaltyProgramUseCase's own docstring for why.
    assert result.data["program"].status == "PENDING_APPROVAL"


def test_create_program_rejects_duplicate_code(conn, auth):
    uc = CreateLoyaltyProgramUseCase(auth)
    uc.execute(conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
               actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    result = uc.execute(
        conn, code="PTS", name="Otro", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success


def test_full_lifecycle(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    program_id = create.entity_id

    approve = ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=program_id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        operation_id=new_uuid())
    assert approve.success
    assert approve.data["program"].status == "PENDING_APPROVAL"

    activate = ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=program_id, actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        operation_id=new_uuid())
    assert activate.success
    assert activate.data["program"].status == "ACTIVE"

    suspend = SuspendLoyaltyProgramUseCase(auth).execute(
        conn, program_id=program_id, reason="Revisión", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert suspend.success
    assert suspend.data["program"].status == "SUSPENDED"

    repo = LoyaltyProgramRepository(conn)
    assert repo.get(program_id).status.value == "SUSPENDED"


def test_activate_without_approval_fails(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    result = ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success
    assert result.error_code == "PROGRAM_INVALID_STATE"


def test_program_not_found(conn, auth):
    result = ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=new_uuid(), actor_user_id=new_uuid(), actor_branch_id=new_uuid(),
        operation_id=new_uuid())
    assert not result.success
    assert result.error_code == "PROGRAM_NOT_FOUND"


def test_permission_denied_when_no_checker():
    conn = sqlite3.connect(":memory:")
    create_loyalty_schema(conn)
    conn.commit()
    uc = CreateLoyaltyProgramUseCase(LoyaltyAuthorizationPolicy())
    result = uc.execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success
    assert result.error_code == "CONFIGURATION_ERROR"
    conn.close()


def test_activate_and_create_events_land_in_outbox(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())

    events = conn.execute(
        "SELECT event_name FROM loyalty_outbox ORDER BY created_at").fetchall()
    names = [e[0] for e in events]
    assert names == ["LOYALTY_PROGRAM_CREATED", "LOYALTY_PROGRAM_ACTIVATED"]
