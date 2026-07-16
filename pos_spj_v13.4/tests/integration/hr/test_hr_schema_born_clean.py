"""FASE 1 — born-clean UUIDv7 HR schema: constraints and idempotency."""

import sqlite3
from datetime import date, datetime, timezone

import pytest

from backend.infrastructure.db.schema.hr_schema import (
    HR_TABLES,
    LEGACY_HR_TABLES,
    create_hr_schema,
    drop_legacy_hr_tables,
)
from backend.shared.ids import new_uuid

NOW = "2026-07-16T00:00:00+00:00"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    create_hr_schema(connection)
    yield connection
    connection.close()


def _employee(conn):
    emp_id = new_uuid()
    conn.execute(
        "INSERT INTO employees (id, employee_code, first_name, last_name, branch_id,"
        " contract_type, payment_frequency, hire_date, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (emp_id, f"E{emp_id[:6]}", "Ana", "García", new_uuid(),
         "PERMANENT", "SEMIMONTHLY", "2025-01-01", NOW, NOW),
    )
    return emp_id


def _punch(conn, emp_id, *, operation_id=None, source="MANUAL", ref=None, ptype="ENTRY"):
    conn.execute(
        "INSERT INTO attendance_punches (id, employee_id, branch_id, punch_type,"
        " occurred_at, source, source_reference_id, operation_id, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (new_uuid(), emp_id, new_uuid(), ptype, NOW, source, ref,
         operation_id or new_uuid(), NOW),
    )


class TestBornClean:
    def test_all_tables_created(self, conn):
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in HR_TABLES:
            assert table in existing, f"missing {table}"

    def test_idempotent(self, conn):
        create_hr_schema(conn)

    def test_no_autoincrement(self, conn):
        for row in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"):
            assert "AUTOINCREMENT" not in row[0].upper()

    def test_all_pks_text(self, conn):
        for table in HR_TABLES:
            for col in conn.execute(f"PRAGMA table_info({table})"):
                if col[5]:  # pk
                    assert col[2] == "TEXT", f"{table}.{col[1]} pk is {col[2]}"

    def test_money_columns_text(self, conn):
        money = {"base_salary", "daily_salary", "amount", "gross_amount",
                 "deductions_amount", "net_amount"}
        for table in HR_TABLES:
            for col in conn.execute(f"PRAGMA table_info({table})"):
                if col[1] in money:
                    assert col[2] == "TEXT", f"{table}.{col[1]} must be TEXT"


class TestIdempotencyConstraints:
    def test_duplicate_punch_operation_id_rejected(self, conn):
        emp = _employee(conn)
        op = new_uuid()
        _punch(conn, emp, operation_id=op)
        with pytest.raises(sqlite3.IntegrityError):
            _punch(conn, emp, operation_id=op)

    def test_duplicate_cash_source_reference_rejected(self, conn):
        emp = _employee(conn)
        ref = new_uuid()
        _punch(conn, emp, source="CASH_REGISTER", ref=ref, ptype="ENTRY")
        with pytest.raises(sqlite3.IntegrityError):
            _punch(conn, emp, source="CASH_REGISTER", ref=ref, ptype="ENTRY")

    def test_same_reference_different_punch_type_allowed(self, conn):
        emp = _employee(conn)
        ref = new_uuid()
        _punch(conn, emp, source="CASH_REGISTER", ref=ref, ptype="ENTRY")
        _punch(conn, emp, source="CASH_REGISTER", ref=ref, ptype="EXIT")  # ok

    def test_unique_workday_per_employee_date(self, conn):
        emp = _employee(conn)
        for _ in range(1):
            conn.execute(
                "INSERT INTO attendance_workdays (id, employee_id, branch_id, work_date,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (new_uuid(), emp, new_uuid(), "2026-07-16", NOW, NOW))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO attendance_workdays (id, employee_id, branch_id, work_date,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (new_uuid(), emp, new_uuid(), "2026-07-16", NOW, NOW))

    def test_status_check_constraint(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO payroll_runs (id, period_start, period_end, status,"
                " operation_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (new_uuid(), "2026-07-01", "2026-07-15", "INVALID",
                 new_uuid(), NOW, NOW))

    def test_foreign_key_enforced(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            _punch(conn, new_uuid())  # non-existent employee


class TestLegacyDrop:
    def test_migration_118_end_to_end(self):
        import importlib
        migration = importlib.import_module(
            "migrations.standalone.118_hr_bounded_context_schema")
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE asistencias (id INTEGER PRIMARY KEY, x REAL)")
        conn.execute("CREATE TABLE nomina_records (id INTEGER PRIMARY KEY, y REAL)")
        migration.run(conn)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "asistencias" not in tables and "nomina_records" not in tables
        for table in HR_TABLES:
            assert table in tables
        conn.close()

    def test_legacy_list_covers_known_tables(self):
        for table in ("asistencias", "nomina_records", "evaluaciones_personal",
                      "turno_asignaciones"):
            assert table in LEGACY_HR_TABLES

    def test_personal_not_dropped(self):
        """personal se conserva hasta el refactor de drivers/comisiones."""
        assert "personal" not in LEGACY_HR_TABLES
        assert "nomina_pagos" not in LEGACY_HR_TABLES  # escrito por el bridge financiero
