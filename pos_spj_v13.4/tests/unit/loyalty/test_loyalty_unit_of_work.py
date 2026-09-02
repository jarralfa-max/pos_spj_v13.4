"""LOY-4 — LoyaltyUnitOfWork transaction boundary. Mirrors
tests/unit/test_sales_unit_of_work.py's style (row-count assertions across
commit/rollback boundaries)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.entities.loyalty_transaction import LoyaltyTransaction
from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork
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


class TestCommitOnCleanExit:
    def test_account_and_transaction_committed_together(self, conn):
        account = LoyaltyAccount.create(new_uuid())
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid())

        with LoyaltyUnitOfWork(conn) as uow:
            uow.accounts.save(account)
            uow.transactions.save(earn)

        row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_accounts WHERE id=?", (account.id,)).fetchone()
        assert row[0] == 1
        txn_row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_transactions WHERE id=?", (earn.id,)).fetchone()
        assert txn_row[0] == 1

    def test_outbox_event_committed_in_same_transaction(self, conn):
        account = LoyaltyAccount.create(new_uuid())
        with LoyaltyUnitOfWork(conn) as uow:
            uow.accounts.save(account)
            uow.outbox.enqueue(
                event_id=new_uuid(), event_name="LOYALTY_POINTS_ISSUED",
                payload_json="{}", operation_id=new_uuid())

        pending = conn.execute(
            "SELECT COUNT(*) FROM loyalty_outbox WHERE status='PENDING'").fetchone()
        assert pending[0] == 1


class TestRollbackOnException:
    def test_exception_rolls_back_account_and_transaction_together(self, conn):
        account = LoyaltyAccount.create(new_uuid())
        earn = LoyaltyTransaction.earn(
            loyalty_account_id=account.id, points_amount=Decimal("100"),
            operation_id=new_uuid())

        with pytest.raises(RuntimeError):
            with LoyaltyUnitOfWork(conn) as uow:
                uow.accounts.save(account)
                uow.transactions.save(earn)
                raise RuntimeError("simulated failure mid-transaction")

        row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_accounts WHERE id=?", (account.id,)).fetchone()
        assert row[0] == 0
        txn_row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_transactions WHERE id=?", (earn.id,)).fetchone()
        assert txn_row[0] == 0

    def test_duplicate_operation_id_is_atomic(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        create_loyalty_schema(conn)
        conn.commit()
        try:
            account = LoyaltyAccount.create(new_uuid())
            op_id = new_uuid()
            with LoyaltyUnitOfWork(conn) as uow:
                uow.accounts.save(account)
                uow.transactions.save(LoyaltyTransaction.earn(
                    loyalty_account_id=account.id, points_amount=Decimal("100"),
                    operation_id=op_id))

            second_account = LoyaltyAccount.create(new_uuid())
            with pytest.raises(sqlite3.IntegrityError):
                with LoyaltyUnitOfWork(conn) as uow:
                    uow.accounts.save(second_account)
                    uow.transactions.save(LoyaltyTransaction.earn(
                        loyalty_account_id=second_account.id, points_amount=Decimal("50"),
                        operation_id=op_id))

            row = conn.execute(
                "SELECT COUNT(*) FROM loyalty_accounts WHERE id=?",
                (second_account.id,)).fetchone()
            assert row[0] == 0
        finally:
            conn.close()


class TestOwnsTransactionFlag:
    def test_owns_transaction_false_never_touches_connection(self, conn):
        account = LoyaltyAccount.create(new_uuid())
        with LoyaltyUnitOfWork(conn, owns_transaction=False) as uow:
            uow.accounts.save(account)
        conn.rollback()
        row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_accounts WHERE id=?", (account.id,)).fetchone()
        assert row[0] == 0

    def test_owns_transaction_true_commits_immediately(self, conn):
        account = LoyaltyAccount.create(new_uuid())
        with LoyaltyUnitOfWork(conn, owns_transaction=True) as uow:
            uow.accounts.save(account)
        conn.rollback()  # no-op — already committed
        row = conn.execute(
            "SELECT COUNT(*) FROM loyalty_accounts WHERE id=?", (account.id,)).fetchone()
        assert row[0] == 1
