"""FASE 2 — born-clean UUIDv7 finance schema: constraints and idempotency."""

import sqlite3
from datetime import date

import pytest

from backend.infrastructure.db.schema.finance_schema import (
    FINANCE_TABLES,
    LEGACY_FINANCE_TABLES,
    create_finance_schema,
    drop_legacy_finance_tables,
)
from backend.shared.ids import new_uuid

NOW = "2026-07-16T00:00:00+00:00"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(connection)
    yield connection
    connection.close()


def _insert_account(conn, code="1101", acc_type="ASSET", normal="DEBIT"):
    account_id = new_uuid()
    conn.execute(
        "INSERT INTO accounts (id, code, name, account_type, normal_balance, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (account_id, code, f"Cuenta {code}", acc_type, normal, NOW, NOW),
    )
    return account_id


def _insert_period(conn, year=2026, month=7):
    period_id = new_uuid()
    conn.execute(
        "INSERT INTO fiscal_periods (id, year, month, opened_at, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)", (period_id, year, month, NOW, NOW, NOW),
    )
    return period_id


def _insert_journal(conn, journal_type="SALES"):
    journal_id = new_uuid()
    conn.execute(
        "INSERT INTO journals (id, journal_type, name, entry_sequence_prefix, created_at)"
        " VALUES (?,?,?,?,?)", (journal_id, journal_type, "Ventas", "SAL", NOW),
    )
    return journal_id


def _insert_entry(conn, journal_id, period_id, *, entry_number="SAL-000001",
                  source_module="sales", source_document_id=None, purpose="SALE_REVENUE",
                  operation_id=None):
    entry_id = new_uuid()
    conn.execute(
        "INSERT INTO journal_entries (id, journal_id, entry_number, entry_date,"
        " fiscal_period_id, source_module, source_document_id, posting_purpose,"
        " operation_id, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, journal_id, entry_number, date(2026, 7, 15).isoformat(), period_id,
         source_module, source_document_id or new_uuid(), purpose,
         operation_id or new_uuid(), NOW, NOW),
    )
    return entry_id


class TestBornCleanSchema:
    def test_all_tables_created(self, conn):
        existing = {
            row["name"] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in FINANCE_TABLES:
            assert table in existing, f"missing table {table}"

    def test_schema_is_idempotent(self, conn):
        create_finance_schema(conn)  # second run must not fail

    def test_no_autoincrement_anywhere(self, conn):
        ddl_rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        for row in ddl_rows:
            assert "AUTOINCREMENT" not in row["sql"].upper()

    def test_all_pks_are_text(self, conn):
        for table in FINANCE_TABLES:
            info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            pks = [col for col in info if col["pk"]]
            for col in pks:
                assert col["type"] == "TEXT", f"{table}.{col['name']} PK is {col['type']}"

    def test_money_columns_are_text_not_real(self, conn):
        money_names = {"debit_amount", "credit_amount", "total_amount", "outstanding_amount",
                       "original_amount", "recognized_amount", "redeemed_amount",
                       "released_amount", "amount", "planned_amount", "committed_amount",
                       "accrued_amount", "acquisition_cost", "residual_value",
                       "accumulated_depreciation", "opening_balance", "closing_balance",
                       "subtotal", "tax_amount", "discount_amount"}
        for table in FINANCE_TABLES:
            for col in conn.execute(f"PRAGMA table_info({table})"):
                if col["name"] in money_names:
                    assert col["type"] == "TEXT", f"{table}.{col['name']} must be TEXT (Decimal string)"


class TestStructuralIdempotency:
    def test_duplicate_operation_id_rejected(self, conn):
        journal = _insert_journal(conn)
        period = _insert_period(conn)
        op = new_uuid()
        _insert_entry(conn, journal, period, operation_id=op)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_entry(conn, journal, period, entry_number="SAL-000002", operation_id=op)

    def test_duplicate_posting_purpose_rejected(self, conn):
        journal = _insert_journal(conn)
        period = _insert_period(conn)
        doc = new_uuid()
        _insert_entry(conn, journal, period, source_document_id=doc)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_entry(conn, journal, period, entry_number="SAL-000002",
                          source_document_id=doc)

    def test_duplicate_instrument_obligation_rejected(self, conn):
        instrument = new_uuid()

        def insert(op_id):
            conn.execute(
                "INSERT INTO commercial_obligations (id, instrument_type, source_module,"
                " source_instrument_id, recognition_basis, original_amount, recognized_amount,"
                " operation_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_uuid(), "GIFT_CARD", "loyalty", instrument, "LIABILITY",
                 "500.00", "500.00", op_id, NOW, NOW),
            )

        insert(new_uuid())
        with pytest.raises(sqlite3.IntegrityError):
            insert(new_uuid())

    def test_status_check_constraints(self, conn):
        journal = _insert_journal(conn)
        period = _insert_period(conn)
        entry = _insert_entry(conn, journal, period)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE journal_entries SET status='INVALID' WHERE id=?", (entry,))

    def test_foreign_keys_enforced(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO journal_lines (id, journal_entry_id, account_id)"
                " VALUES (?,?,?)", (new_uuid(), new_uuid(), new_uuid()),
            )

    def test_unique_fiscal_period(self, conn):
        _insert_period(conn, 2026, 8)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_period(conn, 2026, 8)


class TestLegacyDrop:
    def test_drop_legacy_tables_removes_old_generations(self):
        conn = sqlite3.connect(":memory:")
        # simulate a contaminated dev DB with legacy tables
        conn.execute("CREATE TABLE plan_cuentas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)")
        conn.execute("CREATE TABLE ledger_financiero (id INTEGER PRIMARY KEY, monto REAL)")
        conn.execute("CREATE TABLE journal_entries (id INTEGER PRIMARY KEY, debe REAL, haber REAL)")
        dropped = drop_legacy_finance_tables(conn)
        assert set(dropped) == {"plan_cuentas", "ledger_financiero", "journal_entries"}
        create_finance_schema(conn)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(journal_entries)")}
        assert "operation_id" in cols  # the clean table replaced the legacy one
        conn.close()

    def test_migration_117_runs_end_to_end(self):
        import importlib
        migration = importlib.import_module(
            "migrations.standalone.117_finance_bounded_context_schema"
        )
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE financial_event_log (id INTEGER PRIMARY KEY, monto REAL)")
        migration.run(conn)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "financial_event_log" not in tables
        for table in FINANCE_TABLES:
            assert table in tables
        conn.close()

    def test_legacy_list_covers_known_generations(self):
        for table in ("plan_cuentas", "financial_event_log", "ledger_financiero",
                      "treasury_ledger", "capital_movements", "cuentas_por_cobrar",
                      "accounts_receivable", "accounts_payable", "pagos_cobros"):
            assert table in LEGACY_FINANCE_TABLES
