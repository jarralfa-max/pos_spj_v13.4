from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.commands.hr_commands import CreateEmployeeCommand, DeactivateEmployeeCommand, UpdateEmployeeCommand
from backend.application.use_cases.hr import CreateEmployeeUseCase, DeactivateEmployeeUseCase, UpdateEmployeeUseCase
from backend.application.use_cases.hr.audit import HRAuditRecord
from backend.domain.hr.enums import ContractType, EmploymentStatus, PaymentFrequency
from backend.domain.hr.exceptions import PermissionDeniedError
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.domain.hr.entities import Department, Position
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _setup() -> tuple[sqlite3.Connection, Department, Position]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    department = Department(name="Operaciones", branch_id="01900000-0000-7000-8000-000000000001")
    position = Position(name="Cajera", department_id=department.id)
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    return conn, department, position


def _create_command(department: Department, position: Position, operation_id: str) -> CreateEmployeeCommand:
    return CreateEmployeeCommand(
        operation_id=operation_id,
        branch_id=department.branch_id,
        user_id="01900000-0000-7000-8000-00000000a001",
        employee_code="EMP-003",
        first_name="Carla",
        last_name="Mora",
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1500"),
        daily_salary=Decimal("300"),
        hire_date=date(2026, 3, 1),
    )


class _AuditSink:
    def __init__(self) -> None:
        self.records: list[HRAuditRecord] = []

    def record(self, audit_record: HRAuditRecord) -> None:
        self.records.append(audit_record)


def test_create_update_and_deactivate_employee_use_cases_publish_events_after_persistence() -> None:
    conn, department, position = _setup()
    repository = SQLiteEmployeeRepository(conn)
    bus = InMemoryEventBus()
    audit = _AuditSink()
    published: list[EventName] = []
    for event_name in (EventName.EMPLOYEE_CREATED, EventName.EMPLOYEE_UPDATED, EventName.EMPLOYEE_DEACTIVATED):
        bus.subscribe(event_name, lambda event: published.append(event.event_name))
    allowed = {
        "hr.employee.create",
        "hr.employee.update",
        "hr.employee.deactivate",
    }
    checker = lambda _user_id, permission: permission in allowed

    created = CreateEmployeeUseCase(repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        _create_command(department, position, "01900000-0000-7000-8000-00000000c001")
    )
    assert created.success
    assert created.entity_id is not None
    saved = repository.get(created.entity_id)
    assert saved is not None
    assert saved.employee_code == "EMP-003"

    updated = UpdateEmployeeUseCase(repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        UpdateEmployeeCommand(
            **{
                **_create_command(department, position, "01900000-0000-7000-8000-00000000c002").__dict__,
                "employee_id": created.entity_id,
                "first_name": "Carmen",
            }
        )
    )
    assert updated.success
    assert repository.get(created.entity_id).first_name == "Carmen"  # type: ignore[union-attr]

    deactivated = DeactivateEmployeeUseCase(repository, event_bus=bus, permission_checker=checker, audit_sink=audit).execute(
        DeactivateEmployeeCommand(
            operation_id="01900000-0000-7000-8000-00000000c003",
            branch_id=department.branch_id,
            user_id="01900000-0000-7000-8000-00000000a001",
            employee_id=created.entity_id,
            termination_date=date(2026, 4, 1),
            termination_reason="Fin de contrato",
        )
    )
    assert deactivated.success
    terminated = repository.get(created.entity_id)
    assert terminated is not None
    assert terminated.active is False
    assert terminated.employment_status == EmploymentStatus.TERMINATED
    assert published == [EventName.EMPLOYEE_CREATED, EventName.EMPLOYEE_UPDATED, EventName.EMPLOYEE_DEACTIVATED]
    assert [record.action for record in audit.records] == [
        "HR_EMPLOYEE_CREATED",
        "HR_EMPLOYEE_UPDATED",
        "HR_EMPLOYEE_DEACTIVATED",
    ]
    assert all(record.operation_id.startswith("01900000-") for record in audit.records)
    assert all(record.actor_user_id == "01900000-0000-7000-8000-00000000a001" for record in audit.records)


def test_create_employee_requires_central_permission() -> None:
    conn, department, position = _setup()
    repository = SQLiteEmployeeRepository(conn)
    use_case = CreateEmployeeUseCase(repository, permission_checker=lambda _user_id, _permission: False)

    with pytest.raises(PermissionDeniedError):
        use_case.execute(_create_command(department, position, "01900000-0000-7000-8000-00000000c004"))
