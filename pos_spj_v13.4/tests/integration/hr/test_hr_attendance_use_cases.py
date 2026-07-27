from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.application.commands.attendance_commands import (
    ApproveAttendanceAdjustmentCommand,
    RegisterManualAttendanceCommand,
    RequestAttendanceAdjustmentCommand,
)
from backend.application.use_cases.hr.approve_attendance_adjustment_use_case import ApproveAttendanceAdjustmentUseCase
from backend.application.use_cases.hr.register_manual_attendance_use_case import RegisterManualAttendanceUseCase
from backend.application.use_cases.hr.request_attendance_adjustment_use_case import RequestAttendanceAdjustmentUseCase
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import AdjustmentStatus, ContractType, PaymentFrequency, PunchType
from backend.domain.hr.exceptions import PermissionDeniedError
from backend.infrastructure.db.repositories.attendance_adjustment_repository import SQLiteAttendanceAdjustmentRepository
from backend.infrastructure.db.repositories.attendance_repository import SQLiteAttendanceRepository
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _setup() -> tuple[sqlite3.Connection, Employee]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    department = Department(name="Operaciones", branch_id="01900000-0000-7000-8000-000000000001")
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-004",
        first_name="Diana",
        last_name="Pérez",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1500"),
        daily_salary=Decimal("300"),
        hire_date=date(2026, 5, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    return conn, employee


def _manual_command(employee: Employee, operation_id: str, punch_type: PunchType, occurred_at: datetime) -> RegisterManualAttendanceCommand:
    return RegisterManualAttendanceCommand(
        operation_id=operation_id,
        branch_id=employee.branch_id,
        user_id="01900000-0000-7000-8000-00000000u001",
        employee_id=employee.id,
        punch_type=punch_type,
        occurred_at=occurred_at,
        timezone="UTC",
        reason="Registro autorizado por supervisor",
    )


def test_manual_entry_and_exit_create_immutable_punches_and_calculated_workday() -> None:
    conn, employee = _setup()
    attendance = SQLiteAttendanceRepository(conn)
    bus = InMemoryEventBus()
    published: list[EventName] = []
    for event_name in (EventName.ATTENDANCE_ENTRY_REGISTERED, EventName.ATTENDANCE_EXIT_REGISTERED):
        bus.subscribe(event_name, lambda event: published.append(event.event_name))
    use_case = RegisterManualAttendanceUseCase(
        attendance,
        employee_repository=SQLiteEmployeeRepository(conn),
        event_bus=bus,
        permission_checker=lambda _user_id, permission: permission == "hr.attendance.register_manual",
    )

    entry = use_case.execute(_manual_command(employee, "01900000-0000-7000-8000-00000000d101", PunchType.ENTRY, datetime(2026, 5, 6, 8, 0, tzinfo=UTC)))
    exit_ = use_case.execute(_manual_command(employee, "01900000-0000-7000-8000-00000000d102", PunchType.EXIT, datetime(2026, 5, 6, 16, 30, tzinfo=UTC)))

    assert entry.success and exit_.success
    workday = attendance.get_workday(employee_id=employee.id, branch_id=employee.branch_id, work_date=date(2026, 5, 6))
    assert workday is not None
    assert workday.worked_minutes == 510
    assert workday.status == "COMPLETE"
    assert published == [EventName.ATTENDANCE_ENTRY_REGISTERED, EventName.ATTENDANCE_EXIT_REGISTERED]


def test_duplicate_entry_sequence_does_not_create_second_punch_and_records_incident() -> None:
    conn, employee = _setup()
    attendance = SQLiteAttendanceRepository(conn)
    use_case = RegisterManualAttendanceUseCase(
        attendance,
        employee_repository=SQLiteEmployeeRepository(conn),
        permission_checker=lambda _user_id, _permission: True,
    )
    first = _manual_command(employee, "01900000-0000-7000-8000-00000000d201", PunchType.ENTRY, datetime(2026, 5, 7, 8, 0, tzinfo=UTC))
    duplicate = _manual_command(employee, "01900000-0000-7000-8000-00000000d202", PunchType.ENTRY, datetime(2026, 5, 7, 8, 5, tzinfo=UTC))

    assert use_case.execute(first).success
    result = use_case.execute(duplicate)

    punches = attendance.list_punches_for_workday(employee_id=employee.id, branch_id=employee.branch_id, work_date=date(2026, 5, 7))
    incidents = attendance.list_incidents(employee_id=employee.id, branch_id=employee.branch_id, work_date=date(2026, 5, 7))
    assert len(punches) == 1
    assert result.data["idempotent"] is True
    assert [incident.incident_type.value for incident in incidents] == ["DUPLICATE_IGNORED"]


def test_exit_without_entry_creates_missing_entry_incident_without_inventing_entry() -> None:
    conn, employee = _setup()
    attendance = SQLiteAttendanceRepository(conn)
    use_case = RegisterManualAttendanceUseCase(
        attendance,
        employee_repository=SQLiteEmployeeRepository(conn),
        permission_checker=lambda _user_id, _permission: True,
    )

    result = use_case.execute(_manual_command(employee, "01900000-0000-7000-8000-00000000d301", PunchType.EXIT, datetime(2026, 5, 8, 16, 0, tzinfo=UTC)))

    punches = attendance.list_punches_for_workday(employee_id=employee.id, branch_id=employee.branch_id, work_date=date(2026, 5, 8))
    incidents = attendance.list_incidents(employee_id=employee.id, branch_id=employee.branch_id, work_date=date(2026, 5, 8))
    assert result.success
    assert punches == []
    assert [incident.incident_type.value for incident in incidents] == ["MISSING_ENTRY"]


def test_manual_attendance_requires_permission() -> None:
    conn, employee = _setup()
    use_case = RegisterManualAttendanceUseCase(
        SQLiteAttendanceRepository(conn),
        employee_repository=SQLiteEmployeeRepository(conn),
        permission_checker=lambda _user_id, _permission: False,
    )

    with pytest.raises(PermissionDeniedError):
        use_case.execute(_manual_command(employee, "01900000-0000-7000-8000-00000000d401", PunchType.ENTRY, datetime(2026, 5, 9, 8, 0, tzinfo=UTC)))


def test_attendance_adjustment_request_and_approval_do_not_mutate_original_punch() -> None:
    conn, employee = _setup()
    attendance = SQLiteAttendanceRepository(conn)
    adjustments = SQLiteAttendanceAdjustmentRepository(conn)
    register = RegisterManualAttendanceUseCase(
        attendance,
        employee_repository=SQLiteEmployeeRepository(conn),
        permission_checker=lambda _user_id, _permission: True,
    )
    entry = register.execute(_manual_command(employee, "01900000-0000-7000-8000-00000000d501", PunchType.ENTRY, datetime(2026, 5, 10, 8, 10, tzinfo=UTC)))
    original = attendance.get_punch(entry.entity_id or "")
    assert original is not None

    requested = RequestAttendanceAdjustmentUseCase(
        adjustments,
        attendance,
        permission_checker=lambda _user_id, permission: permission == "hr.attendance.adjust",
    ).execute(
        RequestAttendanceAdjustmentCommand(
            operation_id="01900000-0000-7000-8000-00000000d502",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u001",
            original_punch_id=original.id,
            previous_value=original.occurred_at,
            requested_value=datetime(2026, 5, 10, 8, 0, tzinfo=UTC),
            reason="Corrección autorizada",
        )
    )
    approved = ApproveAttendanceAdjustmentUseCase(
        adjustments,
        permission_checker=lambda _user_id, permission: permission == "hr.attendance.approve_adjustment",
    ).execute(
        ApproveAttendanceAdjustmentCommand(
            operation_id="01900000-0000-7000-8000-00000000d503",
            branch_id=employee.branch_id,
            user_id="01900000-0000-7000-8000-00000000u002",
            adjustment_id=requested.entity_id or "",
        )
    )

    assert approved.success
    adjustment = adjustments.get(requested.entity_id or "")
    assert adjustment is not None
    assert adjustment.status == AdjustmentStatus.APPROVED
    assert attendance.get_punch(original.id).occurred_at == original.occurred_at  # type: ignore[union-attr]
