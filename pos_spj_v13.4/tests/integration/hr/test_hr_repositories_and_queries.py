from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from backend.application.queries.hr_employee_query_service import HREmployeeQueryService
from backend.application.queries.hr_dashboard_query_service import HRDashboardQueryService
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema


def test_employee_repository_roundtrip_and_query_services_use_uuid_strings() -> None:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)

    department = Department(name="Operaciones", branch_id="01900000-0000-7000-8000-000000000001")
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-001",
        first_name="Ana",
        last_name="Pérez",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1000"),
        daily_salary=Decimal("200"),
        hire_date=date(2026, 1, 1),
    )

    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)

    saved = SQLiteEmployeeRepository(conn).get(employee.id)
    assert saved is not None
    assert saved.id == employee.id
    assert isinstance(saved.id, str)

    rows = HREmployeeQueryService(conn).list_employees(search="Ana")
    assert [row.id for row in rows] == [employee.id]
    assert rows[0].full_name == "Ana Pérez"

    dashboard = HRDashboardQueryService(conn).get_dashboard(today=date(2026, 1, 1))
    assert dashboard.active_employees == 1
    assert dashboard.estimated_payroll_cost == Decimal("200")
