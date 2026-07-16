"""Critical final cutover checks for the canonical HR runtime."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.infrastructure.db.schema.hr_schema import create_hr_schema


PACKAGE_ROOT = Path(__file__).resolve().parents[3]


LEGACY_HR_PATHS = (
    "modulos/rrhh.py",
    "modulos/rrhh_turnos.py",
    "core/rrhh",
    "core/services/rrhh_service.py",
    "core/services/rrhh_catalog_service.py",
    "core/services/rrhh_turnos_service.py",
    "core/services/hr_rule_engine.py",
    "core/use_cases/nomina.py",
)


CANONICAL_HR_TABLES = {
    "employees",
    "attendance_punches",
    "attendance_workdays",
    "leave_requests",
    "payroll_runs",
    "payroll_lines",
    "work_shifts",
    "shift_assignments",
}


FORBIDDEN_LEGACY_TABLES = {
    "rrhh_empleados",
    "rrhh_turnos",
    "rrhh_asistencia",
    "nomina",
    "nomina_detalle",
}


def test_final_hr_cutover_uses_only_canonical_runtime_paths() -> None:
    for relative_path in LEGACY_HR_PATHS:
        assert not (PACKAGE_ROOT / relative_path).exists(), relative_path


def test_final_hr_cutover_creates_born_clean_schema_only() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_hr_schema(connection)
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert CANONICAL_HR_TABLES <= table_names
    assert table_names.isdisjoint(FORBIDDEN_LEGACY_TABLES)
