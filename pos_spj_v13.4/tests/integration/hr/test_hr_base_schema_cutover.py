from __future__ import annotations

import sqlite3

from migrations.m000_base_schema import up


CANONICAL_HR_TABLES = {
    "employees",
    "departments",
    "positions",
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

LEGACY_HR_TABLES = {
    "personal",
    "asistencias",
    "nomina_records",
    "nomina_pagos",
    "evaluaciones_personal",
    "turno_roles",
    "turno_asignaciones",
    "turno_notificaciones_log",
    "vacaciones_personal",
}


def test_base_schema_creates_canonical_hr_and_not_legacy_rrhh_tables() -> None:
    conn = sqlite3.connect(":memory:")
    up(conn)

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert CANONICAL_HR_TABLES <= tables
    assert LEGACY_HR_TABLES.isdisjoint(tables)
