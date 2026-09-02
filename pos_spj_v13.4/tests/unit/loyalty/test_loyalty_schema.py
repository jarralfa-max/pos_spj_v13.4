"""LOY-3 — loyalty_schema.py: born-clean UUIDv7 schema, idempotency
constraints, and the real m000 naming collision this phase found and fixed
(a first draft named the program table `loyalty_programs`, colliding with
the legacy Growth Engine table of the same name)."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.loyalty_schema import (
    LOYALTY_TABLES,
    create_loyalty_schema,
    drop_loyalty_schema,
)
from backend.shared.ids import new_uuid


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_loyalty_schema(connection)
    yield connection
    connection.close()


class TestLoyaltySchema:
    def test_creates_all_expected_tables(self, conn):
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in rows}
        for table in LOYALTY_TABLES:
            assert table in names

    def test_does_not_collide_with_legacy_loyalty_programs_name(self, conn):
        """The real collision LOY-3 found: this schema must NEVER create a
        table literally named `loyalty_programs` (that belongs to legacy
        m000_base_schema.py::_create_loyalty)."""
        assert "loyalty_programs" not in LOYALTY_TABLES
        assert "loyalty_program_definitions" in LOYALTY_TABLES

    def test_no_integer_autoincrement_or_real_columns(self, conn):
        for table in LOYALTY_TABLES:
            ddl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            assert "AUTOINCREMENT" not in ddl.upper()
            assert "REAL" not in ddl.upper()
            assert "id TEXT PRIMARY KEY" in ddl

    def test_operation_id_unique_constraint_on_transactions(self, conn):
        account_id = new_uuid()
        conn.execute(
            "INSERT INTO loyalty_accounts (id, customer_id, created_at, updated_at)"
            " VALUES (?, ?, datetime('now'), datetime('now'))",
            (account_id, new_uuid()),
        )
        op_id = new_uuid()
        conn.execute(
            "INSERT INTO loyalty_transactions"
            " (id, loyalty_account_id, transaction_type, points_amount, operation_id, created_at)"
            " VALUES (?, ?, 'EARN', '100', ?, datetime('now'))",
            (new_uuid(), account_id, op_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loyalty_transactions"
                " (id, loyalty_account_id, transaction_type, points_amount, operation_id, created_at)"
                " VALUES (?, ?, 'EARN', '50', ?, datetime('now'))",
                (new_uuid(), account_id, op_id),
            )

    def test_source_document_reason_unique_constraint_blocks_double_accrual(self, conn):
        account_id = new_uuid()
        conn.execute(
            "INSERT INTO loyalty_accounts (id, customer_id, created_at, updated_at)"
            " VALUES (?, ?, datetime('now'), datetime('now'))",
            (account_id, new_uuid()),
        )
        sale_id = new_uuid()
        conn.execute(
            "INSERT INTO loyalty_transactions"
            " (id, loyalty_account_id, transaction_type, points_amount, operation_id,"
            "  source_module, source_document_id, reason_code, created_at)"
            " VALUES (?, ?, 'EARN', '100', ?, 'sales', ?, 'SALE_ACCRUAL', datetime('now'))",
            (new_uuid(), account_id, new_uuid(), sale_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loyalty_transactions"
                " (id, loyalty_account_id, transaction_type, points_amount, operation_id,"
                "  source_module, source_document_id, reason_code, created_at)"
                " VALUES (?, ?, 'EARN', '100', ?, 'sales', ?, 'SALE_ACCRUAL', datetime('now'))",
                (new_uuid(), account_id, new_uuid(), sale_id),
            )

    def test_customer_id_unique_on_accounts(self, conn):
        customer_id = new_uuid()
        conn.execute(
            "INSERT INTO loyalty_accounts (id, customer_id, created_at, updated_at)"
            " VALUES (?, ?, datetime('now'), datetime('now'))",
            (new_uuid(), customer_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO loyalty_accounts (id, customer_id, created_at, updated_at)"
                " VALUES (?, ?, datetime('now'), datetime('now'))",
                (new_uuid(), customer_id),
            )

    def test_drop_schema_removes_all_tables(self, conn):
        dropped = drop_loyalty_schema(conn)
        assert set(dropped) == set(LOYALTY_TABLES)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'loyalty_%'"
        ).fetchall()
        assert rows == []


def test_migration_225_is_registered_and_calls_the_schema_module():
    import importlib

    from migrations.engine import MIGRATIONS

    versions = [m.version for m in MIGRATIONS]
    assert "225" in versions
    migration_225 = importlib.import_module(
        "migrations.standalone.225_loyalty_bounded_context_schema")
    assert migration_225.run is migration_225.up
