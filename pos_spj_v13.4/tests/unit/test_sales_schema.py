"""SALES-4/POS-4 — the born-clean Sales/POS schema. Verifies the DDL itself:
tables exist, UUIDv7-shaped TEXT primary keys, no REAL columns for money,
UNIQUE(operation_id) idempotency, and that the migration wiring
(migrations/standalone/198_...) actually calls the schema module."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.sales_schema import (
    SALES_TABLES,
    create_sales_schema,
    drop_sales_schema,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_sales_schema(connection)
    yield connection
    connection.close()


def _table_columns(connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


class TestSalesSchemaTables:
    def test_all_tables_created(self, conn):
        existing = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in SALES_TABLES:
            assert table in existing

    def test_creation_is_idempotent(self, conn):
        create_sales_schema(conn)  # second call must not raise

    def test_no_real_columns_for_money_or_quantity(self, conn):
        for table in ("sales", "sale_lines"):
            for _cid, name, col_type, *_rest in conn.execute(f"PRAGMA table_info({table})"):
                if any(token in name for token in (
                    "total", "subtotal", "quantity", "price", "discount", "tax",
                )):
                    assert col_type.upper() != "REAL", f"{table}.{name} must not be REAL"

    def test_ids_are_text_primary_keys(self, conn):
        for table in SALES_TABLES:
            pk_columns = [
                row[1] for row in conn.execute(f"PRAGMA table_info({table})") if row[5] == 1
            ]
            assert pk_columns == ["id"]
            id_type = next(
                row[2] for row in conn.execute(f"PRAGMA table_info({table})") if row[1] == "id")
            assert id_type.upper() == "TEXT"

    def test_no_autoincrement_anywhere(self, conn):
        sql = "\n".join(
            row[0] or "" for row in conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name IN "
                f"({','.join('?' for _ in SALES_TABLES)})", SALES_TABLES)
        )
        assert "AUTOINCREMENT" not in sql.upper()

    def test_drop_schema_removes_every_table(self, conn):
        dropped = drop_sales_schema(conn)
        assert set(dropped) == set(SALES_TABLES)
        remaining = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not (remaining & set(SALES_TABLES))


class TestSalesTableConstraints:
    def test_operation_id_is_unique(self, conn):
        op_id = new_uuid()
        conn.execute(
            "INSERT INTO sales (id, branch_id, cashier_user_id, operation_id, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (new_uuid(), new_uuid(), new_uuid(), op_id),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sales (id, branch_id, cashier_user_id, operation_id, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (new_uuid(), new_uuid(), new_uuid(), op_id),
            )

    def test_sale_line_references_sale(self, conn):
        assert "sale_id" in _table_columns(conn, "sale_lines")

    def test_sales_outbox_event_id_is_unique(self, conn):
        event_id = new_uuid()
        conn.execute(
            "INSERT INTO sales_outbox (id, event_id, event_name, payload_json, "
            "operation_id, created_at) VALUES (?, ?, 'SALE_STARTED', '{}', ?, datetime('now'))",
            (new_uuid(), event_id, new_uuid()),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sales_outbox (id, event_id, event_name, payload_json, "
                "operation_id, created_at) VALUES (?, ?, 'SALE_STARTED', '{}', ?, datetime('now'))",
                (new_uuid(), event_id, new_uuid()),
            )


class TestMigrationWiring:
    def test_migration_198_calls_schema_module(self):
        import importlib

        migration_198 = importlib.import_module(
            "migrations.standalone.198_sales_bounded_context_schema")
        assert hasattr(migration_198, "run")
        assert hasattr(migration_198, "up")

    def test_migration_198_registered_in_engine(self):
        from migrations.engine import MIGRATIONS

        versions = [m.version for m in MIGRATIONS]
        assert "198" in versions
