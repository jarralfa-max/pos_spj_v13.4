from __future__ import annotations

import sqlite3
from datetime import date, time
from decimal import Decimal

from backend.application.commands.hr_commands import AssignShiftCommand, CreateRestDayCommand, CreateShiftCommand, CreateShiftTemplateCommand
from backend.application.queries.shift_query_service import ShiftQueryService
from backend.application.use_cases.hr import AssignShiftUseCase, CreateRestDayUseCase, CreateShiftTemplateUseCase, CreateShiftUseCase
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency
from backend.domain.hr.policies.shift_policy import ShiftPolicy
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.repositories.work_shift_repository import SQLiteWorkShiftRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _setup() -> tuple[sqlite3.Connection, Employee]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    branch_id = "01900000-0000-7000-8000-000000000001"
    department = Department(name="Operaciones", branch_id=branch_id)
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-SHIFT",
        first_name="Sofía",
        last_name="Turnos",
        branch_id=branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1500"),
        daily_salary=Decimal("300"),
        hire_date=date(2026, 1, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    return conn, employee


def test_shift_template_assignment_rest_day_and_query_service_flow() -> None:
    conn, employee = _setup()
    repository = SQLiteWorkShiftRepository(conn)
    employee_repository = SQLiteEmployeeRepository(conn)
    bus = InMemoryEventBus()
    published: list[EventName] = []
    bus.subscribe(EventName.WORK_SHIFT_CREATED, lambda event: published.append(event.event_name))
    bus.subscribe(EventName.WORK_SHIFT_ASSIGNED, lambda event: published.append(event.event_name))
    checker = lambda _user_id, permission: permission == "hr.shift.manage"

    shift_result = CreateShiftUseCase(repository, event_bus=bus, permission_checker=checker).execute(
        CreateShiftCommand(
            operation_id="01900000-0000-7000-8000-00000000s001",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            name="Matutino",
            start_time=time(8, 0),
            end_time=time(16, 30),
            break_minutes=30,
            late_tolerance_minutes=10,
        )
    )
    assert shift_result.success

    template_result = CreateShiftTemplateUseCase(repository, permission_checker=checker).execute(
        CreateShiftTemplateCommand(
            operation_id="01900000-0000-7000-8000-00000000s002",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            name="Semana matutina",
            work_shift_id=shift_result.entity_id or "",
            weekdays="MONDAY,TUESDAY,WEDNESDAY,THURSDAY,FRIDAY",
        )
    )
    assert template_result.success

    assignment_result = AssignShiftUseCase(repository, employee_repository, event_bus=bus, permission_checker=checker).execute(
        AssignShiftCommand(
            operation_id="01900000-0000-7000-8000-00000000s003",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            employee_id=employee.id,
            work_shift_id=shift_result.entity_id or "",
            effective_from=date(2026, 7, 1),
            weekdays="MONDAY,TUESDAY,WEDNESDAY,THURSDAY,FRIDAY",
        )
    )
    assert assignment_result.success

    rest_result = CreateRestDayUseCase(repository, permission_checker=checker).execute(
        CreateRestDayCommand(
            operation_id="01900000-0000-7000-8000-00000000s004",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            employee_id=employee.id,
            rest_date=date(2026, 7, 5),
            reason="Descanso semanal",
        )
    )
    assert rest_result.success

    query = ShiftQueryService(conn)
    assert [shift.name for shift in query.list_shifts(branch_id=employee.branch_id)] == ["Matutino"]
    assert [template.name for template in query.list_templates(branch_id=employee.branch_id)] == ["Semana matutina"]
    assert len(query.list_assignments(branch_id=employee.branch_id, employee_id=employee.id)) == 1
    assert [rest.reason for rest in query.list_rest_days(branch_id=employee.branch_id, employee_id=employee.id)] == ["Descanso semanal"]
    assert published == [EventName.WORK_SHIFT_CREATED, EventName.WORK_SHIFT_ASSIGNED]


def test_shift_policy_calculates_late_and_overtime_minutes() -> None:
    conn, employee = _setup()
    repository = SQLiteWorkShiftRepository(conn)
    shift_result = CreateShiftUseCase(repository, permission_checker=lambda _u, _p: True).execute(
        CreateShiftCommand(
            operation_id="01900000-0000-7000-8000-00000000s005",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            name="Vespertino",
            start_time=time(9, 0),
            end_time=time(17, 0),
            late_tolerance_minutes=5,
        )
    )
    shift = repository.get(shift_result.entity_id or "")
    assert shift is not None
    policy = ShiftPolicy()
    from datetime import UTC, datetime

    entry_at = datetime(2026, 7, 16, 9, 12, tzinfo=UTC)
    exit_at = datetime(2026, 7, 16, 17, 45, tzinfo=UTC)
    assert policy.late_minutes(shift, entry_at) == 7
    assert policy.overtime_minutes(shift, entry_at, exit_at) == 45
