from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.commands.hr_commands import ApproveLeaveCommand, CancelLeaveCommand, RejectLeaveCommand, RequestLeaveCommand
from backend.application.queries.leave_query_service import LeaveQueryService
from backend.application.use_cases.hr import ApproveLeaveUseCase, CancelLeaveUseCase, RejectLeaveUseCase, RequestLeaveUseCase
from backend.application.use_cases.hr.audit import HRAuditRecord
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, LeaveStatus, LeaveType, PaymentFrequency
from backend.domain.hr.exceptions import InsufficientLeaveBalanceError, LeaveOverlapError
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.leave_repository import SQLiteLeaveRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


class _AuditSink:
    def __init__(self) -> None:
        self.records: list[HRAuditRecord] = []

    def record(self, audit_record: HRAuditRecord) -> None:
        self.records.append(audit_record)


def _setup() -> tuple[sqlite3.Connection, Employee, SQLiteLeaveRepository]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    branch_id = "01900000-0000-7000-8000-000000000001"
    department = Department(name="Operaciones", branch_id=branch_id)
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-LEAVE",
        first_name="Laura",
        last_name="Permisos",
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
    leave_repository = SQLiteLeaveRepository(conn)
    leave_repository.set_balance(employee_id=employee.id, branch_id=employee.branch_id, leave_type=LeaveType.VACATION, available_days=Decimal("10"))
    return conn, employee, leave_repository


def _request_command(employee: Employee, operation_id: str, start: date, end: date) -> RequestLeaveCommand:
    return RequestLeaveCommand(
        operation_id=operation_id,
        branch_id=employee.branch_id,
        user_id="01900000-0000-7000-8000-00000000u001",
        employee_id=employee.id,
        leave_type=LeaveType.VACATION,
        start_date=start,
        end_date=end,
        reason="Vacaciones familiares",
    )


def test_request_approve_reject_cancel_leave_flow_with_history_events_and_audit() -> None:
    conn, employee, leave_repository = _setup()
    bus = InMemoryEventBus()
    audit = _AuditSink()
    published: list[EventName] = []
    for event_name in (EventName.LEAVE_REQUESTED, EventName.LEAVE_APPROVED, EventName.LEAVE_REJECTED, EventName.LEAVE_CANCELLED):
        bus.subscribe(event_name, lambda event: published.append(event.event_name))
    checker = lambda _user_id, permission: permission in {"hr.leave.request", "hr.leave.approve"}
    employee_repository = SQLiteEmployeeRepository(conn)

    request_result = RequestLeaveUseCase(leave_repository, employee_repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        _request_command(employee, "01900000-0000-7000-8000-00000000l001", date(2026, 8, 1), date(2026, 8, 3))
    )
    assert request_result.success

    approve_result = ApproveLeaveUseCase(leave_repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        ApproveLeaveCommand(operation_id="01900000-0000-7000-8000-00000000l002", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u002", leave_request_id=request_result.entity_id or "")
    )
    assert approve_result.success
    approved = leave_repository.get(request_result.entity_id or "")
    assert approved is not None
    assert approved.status == LeaveStatus.APPROVED
    assert leave_repository.get_available_days(employee_id=employee.id, branch_id=employee.branch_id, leave_type=LeaveType.VACATION) == Decimal("7")

    reject_source = RequestLeaveUseCase(leave_repository, employee_repository, permission_checker=checker).execute(
        _request_command(employee, "01900000-0000-7000-8000-00000000l003", date(2026, 9, 1), date(2026, 9, 1))
    )
    RejectLeaveUseCase(leave_repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        RejectLeaveCommand(operation_id="01900000-0000-7000-8000-00000000l004", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u002", leave_request_id=reject_source.entity_id or "", reason="Cobertura insuficiente")
    )

    cancel_source = RequestLeaveUseCase(leave_repository, employee_repository, permission_checker=checker).execute(
        _request_command(employee, "01900000-0000-7000-8000-00000000l005", date(2026, 10, 1), date(2026, 10, 1))
    )
    CancelLeaveUseCase(leave_repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        CancelLeaveCommand(operation_id="01900000-0000-7000-8000-00000000l006", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u001", leave_request_id=cancel_source.entity_id or "", reason="Cambio de planes")
    )

    query = LeaveQueryService(conn)
    assert [row.status for row in query.list_requests(branch_id=employee.branch_id)] == ["CANCELLED", "REJECTED", "APPROVED"]
    assert [row.new_status for row in query.list_history(leave_request_id=request_result.entity_id or "")] == ["PENDING", "APPROVED"]
    assert published == [EventName.LEAVE_REQUESTED, EventName.LEAVE_APPROVED, EventName.LEAVE_REJECTED, EventName.LEAVE_CANCELLED]
    assert [record.action for record in audit.records] == ["LEAVE_REQUESTED", "LEAVE_APPROVED", "LEAVE_REJECTED", "LEAVE_CANCELLED"]


def test_leave_request_validates_overlap_and_balance() -> None:
    conn, employee, leave_repository = _setup()
    employee_repository = SQLiteEmployeeRepository(conn)
    checker = lambda _user_id, permission: permission == "hr.leave.request"
    use_case = RequestLeaveUseCase(leave_repository, employee_repository, permission_checker=checker)
    use_case.execute(_request_command(employee, "01900000-0000-7000-8000-00000000l010", date(2026, 11, 1), date(2026, 11, 3)))

    with pytest.raises(LeaveOverlapError):
        use_case.execute(_request_command(employee, "01900000-0000-7000-8000-00000000l011", date(2026, 11, 2), date(2026, 11, 4)))

    with pytest.raises(InsufficientLeaveBalanceError):
        use_case.execute(_request_command(employee, "01900000-0000-7000-8000-00000000l012", date(2026, 12, 1), date(2026, 12, 15)))
