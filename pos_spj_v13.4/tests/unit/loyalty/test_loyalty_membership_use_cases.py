"""LOY-5 — LoyaltyMembership use cases: Enroll, Suspend, Close."""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.loyalty.use_cases.membership_use_cases import (
    CloseLoyaltyMembershipUseCase,
    EnrollLoyaltyMembershipUseCase,
    SuspendLoyaltyMembershipUseCase,
)
from backend.application.loyalty.use_cases.program_use_cases import (
    ActivateLoyaltyProgramUseCase,
    ApproveLoyaltyProgramUseCase,
    CreateLoyaltyProgramUseCase,
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


def test_enroll_creates_account_and_membership(conn, auth):
    program_id = _active_program(conn, auth)
    customer_id = new_uuid()
    result = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert result.success
    assert result.data["membership"].status == "ACTIVE"

    account_row = conn.execute(
        "SELECT id FROM loyalty_accounts WHERE customer_id=?", (customer_id,)).fetchone()
    assert account_row is not None


def test_enroll_reuses_existing_account_for_second_program(conn, auth):
    program_a = _active_program(conn, auth)
    create_b = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="VIP", name="VIP", currency_name="Puntos",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    ApproveLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create_b.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    ActivateLoyaltyProgramUseCase(auth).execute(
        conn, program_id=create_b.entity_id, actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    program_b = create_b.entity_id

    customer_id = new_uuid()
    EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_a,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_b,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())

    accounts = conn.execute(
        "SELECT COUNT(*) FROM loyalty_accounts WHERE customer_id=?", (customer_id,)).fetchone()
    assert accounts[0] == 1
    memberships = conn.execute(
        "SELECT COUNT(*) FROM loyalty_memberships").fetchone()
    assert memberships[0] == 2


def test_enroll_rejects_inactive_program(conn, auth):
    create = CreateLoyaltyProgramUseCase(auth).execute(
        conn, code="PTS", name="Puntos SPJ", currency_name="Estrellas",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    result = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=new_uuid(), program_id=create.entity_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success
    assert result.error_code == "PROGRAM_INACTIVE"


def test_enroll_rejects_duplicate_enrollment(conn, auth):
    program_id = _active_program(conn, auth)
    customer_id = new_uuid()
    EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    result = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=customer_id, program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success


def test_suspend_and_close(conn, auth):
    program_id = _active_program(conn, auth)
    enroll = EnrollLoyaltyMembershipUseCase(auth).execute(
        conn, customer_id=new_uuid(), program_id=program_id,
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    membership_id = enroll.entity_id

    suspend = SuspendLoyaltyMembershipUseCase(auth).execute(
        conn, membership_id=membership_id, reason="Revisión", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert suspend.success
    assert suspend.data["membership"].status == "SUSPENDED"

    close = CloseLoyaltyMembershipUseCase(auth).execute(
        conn, membership_id=membership_id, reason="Cliente solicitó baja",
        actor_user_id=new_uuid(), actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert close.success
    assert close.data["membership"].status == "CLOSED"


def test_membership_not_found(conn, auth):
    result = SuspendLoyaltyMembershipUseCase(auth).execute(
        conn, membership_id=new_uuid(), reason="x", actor_user_id=new_uuid(),
        actor_branch_id=new_uuid(), operation_id=new_uuid())
    assert not result.success
    assert result.error_code == "MEMBERSHIP_NOT_FOUND"
