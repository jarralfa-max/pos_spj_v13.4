"""LOY-4 — Loyalty repositories: round-trip persistence for
Program/Account/Membership/Transaction against the LOY-3 schema."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.entities.loyalty_program import LoyaltyProgram
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.domain.loyalty.enums import (
    AccountStatus,
    MembershipStatus,
    ProgramStatus,
    TransactionStatus,
    TransactionType,
)
from backend.infrastructure.db.repositories.loyalty.account_repository import (
    LoyaltyAccountRepository,
)
from backend.infrastructure.db.repositories.loyalty.membership_repository import (
    LoyaltyMembershipRepository,
)
from backend.infrastructure.db.repositories.loyalty.program_repository import (
    LoyaltyProgramRepository,
)
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


class TestLoyaltyProgramRepository:
    def test_round_trip(self, conn):
        repo = LoyaltyProgramRepository(conn)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        repo.save(program)

        fetched = repo.get(program.id)
        assert fetched is not None
        assert fetched.code == "PTS"
        assert fetched.status is ProgramStatus.DRAFT
        assert fetched.earning_enabled is True

    def test_get_by_code(self, conn):
        repo = LoyaltyProgramRepository(conn)
        program = LoyaltyProgram.create("VIP", "VIP Rewards", "Puntos")
        repo.save(program)
        assert repo.get_by_code("VIP").id == program.id
        assert repo.get_by_code("NOPE") is None

    def test_update_persists_lifecycle_change(self, conn):
        repo = LoyaltyProgramRepository(conn)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        repo.save(program)
        program.submit_for_approval()
        program.approve("supervisor-1")
        program.activate()
        repo.save(program)

        fetched = repo.get(program.id)
        assert fetched.status is ProgramStatus.ACTIVE
        assert fetched.approved_by_user_id == "supervisor-1"

    def test_list_active_excludes_draft(self, conn):
        repo = LoyaltyProgramRepository(conn)
        draft = LoyaltyProgram.create("DFT", "Borrador", "Puntos")
        repo.save(draft)
        active = LoyaltyProgram.create("ACT", "Activo", "Puntos")
        active.submit_for_approval()
        active.approve("supervisor-1")
        active.activate()
        repo.save(active)

        results = repo.list_active()
        assert [p.id for p in results] == [active.id]


class TestLoyaltyAccountRepository:
    def test_round_trip(self, conn):
        repo = LoyaltyAccountRepository(conn)
        customer_id = new_uuid()
        account = LoyaltyAccount.create(customer_id)
        repo.save(account)

        fetched = repo.get(account.id)
        assert fetched is not None
        assert fetched.customer_id == customer_id
        assert fetched.status is AccountStatus.ACTIVE

    def test_get_by_customer_id(self, conn):
        repo = LoyaltyAccountRepository(conn)
        customer_id = new_uuid()
        account = LoyaltyAccount.create(customer_id)
        repo.save(account)
        assert repo.get_by_customer_id(customer_id).id == account.id

    def test_duplicate_customer_id_violates_unique_constraint(self, conn):
        repo = LoyaltyAccountRepository(conn)
        customer_id = new_uuid()
        repo.save(LoyaltyAccount.create(customer_id))
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(LoyaltyAccount.create(customer_id))

    def test_suspend_persists(self, conn):
        repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        repo.save(account)
        account.suspend("Fraude sospechado")
        repo.save(account)
        assert repo.get(account.id).status is AccountStatus.SUSPENDED


class TestLoyaltyMembershipRepository:
    def test_round_trip(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        program_repo = LoyaltyProgramRepository(conn)
        membership_repo = LoyaltyMembershipRepository(conn)

        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        program_repo.save(program)

        membership = LoyaltyMembership.enroll(account.id, program.id)
        membership_repo.save(membership)

        fetched = membership_repo.get(membership.id)
        assert fetched is not None
        assert fetched.status is MembershipStatus.ACTIVE
        assert fetched.current_tier_id is None

    def test_get_by_account_and_program(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        program_repo = LoyaltyProgramRepository(conn)
        membership_repo = LoyaltyMembershipRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        program_repo.save(program)
        membership = LoyaltyMembership.enroll(account.id, program.id)
        membership_repo.save(membership)

        found = membership_repo.get_by_account_and_program(account.id, program.id)
        assert found.id == membership.id

    def test_duplicate_enrollment_violates_unique_constraint(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        program_repo = LoyaltyProgramRepository(conn)
        membership_repo = LoyaltyMembershipRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        program_repo.save(program)
        membership_repo.save(LoyaltyMembership.enroll(account.id, program.id))
        with pytest.raises(sqlite3.IntegrityError):
            membership_repo.save(LoyaltyMembership.enroll(account.id, program.id))

    def test_change_tier_persists(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        program_repo = LoyaltyProgramRepository(conn)
        membership_repo = LoyaltyMembershipRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        program = LoyaltyProgram.create("PTS", "Puntos SPJ", "Estrellas")
        program_repo.save(program)
        membership = LoyaltyMembership.enroll(account.id, program.id)
        membership_repo.save(membership)

        tier_id = new_uuid()
        membership.change_tier(tier_id)
        membership_repo.save(membership)
        assert membership_repo.get(membership.id).current_tier_id == tier_id


class TestLoyaltyTransactionRepository:
    def test_round_trip_preserves_decimal(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)

        repo = LoyaltyTransactionRepository(conn)
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("123.45"),
            operation_id=new_uuid())
        repo.save(earn)

        fetched = repo.get(earn.id)
        assert fetched is not None
        assert fetched.points_amount == Decimal("123.45")
        assert isinstance(fetched.points_amount, Decimal)
        assert fetched.transaction_type is TransactionType.EARN
        assert fetched.status is TransactionStatus.AVAILABLE

    def test_get_by_operation_id(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        op_id = new_uuid()
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("10"), operation_id=op_id)
        repo.save(earn)
        assert repo.get_by_operation_id(op_id).id == earn.id

    def test_duplicate_operation_id_violates_unique_constraint(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        op_id = new_uuid()
        repo.save(LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("10"), operation_id=op_id))
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(LoyaltyTransaction.earn(
                loyalty_account_id=account.id, points_amount=Decimal("5"), operation_id=op_id))

    def test_status_update_never_touches_points_amount(self, conn):
        """The repository's own idempotency guarantee: even if a caller
        tried to re-save a mutated points_amount, only status/
        reversal_transaction_id are ever written on conflict."""
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=account.id, points_amount=Decimal("-30"),
            operation_id=new_uuid())
        repo.save(reservation)

        reservation.mark_consumed()
        reservation.points_amount = Decimal("-999")  # simulate a rogue caller
        repo.save(reservation)

        fetched = repo.get(reservation.id)
        assert fetched.status is TransactionStatus.CONSUMED
        assert fetched.points_amount == Decimal("-30")  # unchanged, not -999

    def test_exists_for_source_matches_null_document_id(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        adjustment = LoyaltyTransaction.adjustment(
            loyalty_account_id=account.id, points_amount=Decimal("5"),
            operation_id=new_uuid(), reason_code="CORRECCION",
            source_module="manual")
        repo.save(adjustment)

        assert repo.exists_for_source(
            source_module="manual", source_document_id=None,
            transaction_type=TransactionType.ADJUSTMENT, reason_code="CORRECCION") is True
        assert repo.exists_for_source(
            source_module="manual", source_document_id=None,
            transaction_type=TransactionType.EARN, reason_code="CORRECCION") is False

    def test_exists_for_source_blocks_double_accrual(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        sale_id = new_uuid()
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid(), source_module="sales",
            source_document_id=sale_id, reason_code="SALE_ACCRUAL")
        repo.save(earn)

        assert repo.exists_for_source(
            source_module="sales", source_document_id=sale_id,
            transaction_type=TransactionType.EARN, reason_code="SALE_ACCRUAL") is True

    def test_list_for_account_orders_by_created_at(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid())
        redeem = LoyaltyTransaction.redeem(
            loyalty_account_id=account.id, points_amount=Decimal("-40"),
            operation_id=new_uuid())
        repo.save(earn)
        repo.save(redeem)

        ledger = repo.list_for_account(account.id)
        assert [t.id for t in ledger] == [earn.id, redeem.id]

    def test_list_reserved_for_account(self, conn):
        account_repo = LoyaltyAccountRepository(conn)
        account = LoyaltyAccount.create(new_uuid())
        account_repo.save(account)
        repo = LoyaltyTransactionRepository(conn)
        reservation = LoyaltyTransaction.reserve(
            loyalty_account_id=account.id, points_amount=Decimal("-20"),
            operation_id=new_uuid())
        repo.save(reservation)
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid())
        repo.save(earn)

        reserved = repo.list_reserved_for_account(account.id)
        assert [t.id for t in reserved] == [reservation.id]
