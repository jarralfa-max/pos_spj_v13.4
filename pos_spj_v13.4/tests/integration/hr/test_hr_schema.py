from __future__ import annotations

import sqlite3

from backend.infrastructure.db.schema.hr_schema import create_hr_schema


HR_TABLES = {
    "employees",
    "departments",
    "positions",
    "payment_frequencies",
    "contract_types",
    "work_shifts",
    "shift_assignments",
    "attendance_punches",
    "attendance_workdays",
    "attendance_adjustments",
    "leave_requests",
    "payroll_runs",
    "payroll_lines",
    "payroll_concepts",
    "payroll_payments",
}


def test_hr_schema_uses_text_not_null_primary_keys_and_foreign_keys() -> None:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)

    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert HR_TABLES <= existing

    for table in HR_TABLES:
        columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        pk_columns = [column for column in columns if column[5] == 1]
        assert len(pk_columns) == 1, table
        _, name, column_type, not_null, *_ = pk_columns[0]
        assert name == "id"
        assert column_type.upper() == "TEXT"
        assert not_null == 1

    employee_fks = conn.execute('PRAGMA foreign_key_list("employees")').fetchall()
    assert {fk[2] for fk in employee_fks} >= {"departments", "positions", "employees"}
