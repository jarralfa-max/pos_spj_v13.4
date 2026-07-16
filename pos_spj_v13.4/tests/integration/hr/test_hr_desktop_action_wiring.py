from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from core.ui.hr_module_factory import _HRActionWiring
from backend.domain.hr.entities import Department, Position
from backend.domain.hr.exceptions import PermissionDeniedError
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from frontend.desktop.modules.hr.hr_view_models import HREmployeeFormViewModel


@dataclass
class _Session:
    user_id: str = "01900000-0000-7000-8000-00000000a001"
    usuario: str = "ana"
    active_branch_id: str = "01900000-0000-7000-8000-000000000001"
    sucursal_id: str = "01900000-0000-7000-8000-000000000001"
    is_active: bool = True
    allowed: bool = True

    def tiene_permiso(self, _permission: str) -> bool:
        return self.allowed


def _setup() -> tuple[sqlite3.Connection, Department, Position]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    department = Department(name="Operaciones", branch_id="01900000-0000-7000-8000-000000000001")
    position = Position(name="Cajera", department_id=department.id)
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    return conn, department, position


def _form(department: Department, position: Position) -> HREmployeeFormViewModel:
    return HREmployeeFormViewModel(
        employee_code="EMP-020",
        first_name="Laura",
        last_name="Ríos",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type="FULL_TIME",
        payment_frequency="WEEKLY",
        base_salary=Decimal("2500"),
        daily_salary=Decimal("500"),
        hire_date=date(2026, 6, 1),
        phone_e164="+5215555555555",
        email="laura@example.test",
    )


def test_hr_desktop_action_wiring_creates_employee_through_use_case() -> None:
    conn, department, position = _setup()
    wiring = _HRActionWiring(conn, _Session())

    wiring.create_employee(_form(department, position))

    row = conn.execute("SELECT employee_code, first_name, department_id, position_id FROM employees").fetchone()
    assert row == ("EMP-020", "Laura", department.id, position.id)


def test_hr_desktop_action_wiring_defaults_missing_enum_catalog_values() -> None:
    conn, department, position = _setup()
    wiring = _HRActionWiring(conn, _Session())
    form = HREmployeeFormViewModel(
        employee_code="EMP-020",
        first_name="Laura",
        last_name="Ríos",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=None,  # type: ignore[arg-type]
        payment_frequency=None,  # type: ignore[arg-type]
        base_salary=Decimal("2500"),
        daily_salary=Decimal("500"),
        hire_date=date(2026, 6, 1),
    )

    wiring.create_employee(form)

    row = conn.execute(
        "SELECT contract_type, payment_frequency FROM employees WHERE employee_code = ?",
        ("EMP-020",),
    ).fetchone()
    assert row == ("FULL_TIME", "WEEKLY")


def test_hr_desktop_action_wiring_uses_central_permission_checker() -> None:
    conn, department, position = _setup()
    wiring = _HRActionWiring(conn, _Session(allowed=False))

    with pytest.raises(PermissionDeniedError):
        wiring.create_employee(_form(department, position))


def test_hr_desktop_action_wiring_updates_and_deactivates_employee_through_use_cases() -> None:
    conn, department, position = _setup()
    wiring = _HRActionWiring(conn, _Session())
    form = _form(department, position)
    wiring.create_employee(form)
    employee_id = conn.execute("SELECT id FROM employees WHERE employee_code = ?", ("EMP-020",)).fetchone()[0]

    updated_form = HREmployeeFormViewModel(
        employee_code="EMP-020",
        first_name="Laura Elena",
        last_name="Ríos",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type="FULL_TIME",
        payment_frequency="WEEKLY",
        base_salary=Decimal("2600"),
        daily_salary=Decimal("520"),
        hire_date=date(2026, 6, 1),
    )
    wiring.update_employee(employee_id, updated_form)
    wiring.deactivate_employee(employee_id, "Fin de contrato")

    row = conn.execute("SELECT first_name, active, employment_status, termination_reason FROM employees WHERE id = ?", (employee_id,)).fetchone()
    assert row == ("Laura Elena", 0, "TERMINATED", "Fin de contrato")
