from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.commands.hr_commands import AuthorizePayrollRunCommand, CancelPayrollRunCommand, GeneratePayrollRunCommand, PayPayrollRunCommand
from backend.application.queries.payroll_query_service import PayrollQueryService
from backend.application.use_cases.hr import AuthorizePayrollRunUseCase, CancelPayrollRunUseCase, GeneratePayrollRunUseCase, PayPayrollRunUseCase
from backend.domain.hr.entities import Department, Employee, Position
from backend.domain.hr.enums import ContractType, PaymentFrequency, PayrollRunStatus
from backend.domain.hr.exceptions import PayrollAlreadyPaidError, PayrollNotAuthorizedError
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.payroll_payment_repository import SQLitePayrollPaymentRepository
from backend.infrastructure.db.repositories.payroll_repository import SQLitePayrollRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


def _setup() -> tuple[sqlite3.Connection, Employee, SQLitePayrollRepository, SQLitePayrollPaymentRepository]:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    branch_id = "01900000-0000-7000-8000-000000000001"
    department = Department(name="Operaciones", branch_id=branch_id)
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-PAYROLL",
        first_name="Paula",
        last_name="Nómina",
        branch_id=branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("3000"),
        daily_salary=Decimal("300"),
        hire_date=date(2026, 1, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    return conn, employee, SQLitePayrollRepository(conn), SQLitePayrollPaymentRepository(conn)


def _generate_command(employee: Employee, operation_id: str) -> GeneratePayrollRunCommand:
    return GeneratePayrollRunCommand(
        operation_id=operation_id,
        branch_id=employee.branch_id,
        user_id="01900000-0000-7000-8000-00000000u001",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7),
        employee_ids=(employee.id,),
    )


def test_generate_authorize_pay_payroll_once_and_publish_single_finance_event() -> None:
    conn, employee, payroll_repository, payment_repository = _setup()
    bus = InMemoryEventBus()
    paid_events = []
    bus.subscribe(EventName.PAYROLL_PAID, lambda event: paid_events.append(event))
    checker = lambda _user_id, permission: permission in {"hr.payroll.generate", "hr.payroll.authorize", "hr.payroll.pay", "hr.payroll.cancel"}
    employee_repository = SQLiteEmployeeRepository(conn)

    generated = GeneratePayrollRunUseCase(payroll_repository, employee_repository, event_bus=bus, permission_checker=checker).execute(
        _generate_command(employee, "01900000-0000-7000-8000-00000000p001")
    )
    assert generated.success
    payroll_run = payroll_repository.get_run(generated.entity_id or "")
    assert payroll_run is not None
    assert payroll_run.status == PayrollRunStatus.CALCULATED
    assert payroll_run.net_amount == Decimal("2100")
    assert len(payroll_repository.list_lines(payroll_run.id)) == 1
    assert len(payroll_repository.list_concepts(payroll_repository.list_lines(payroll_run.id)[0].id)) == 1

    authorized = AuthorizePayrollRunUseCase(payroll_repository, event_bus=bus, permission_checker=checker).execute(
        AuthorizePayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p002", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u002", payroll_run_id=payroll_run.id)
    )
    assert authorized.success

    paid = PayPayrollRunUseCase(payroll_repository, payment_repository, event_bus=bus, permission_checker=checker).execute(
        PayPayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p003", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u003", payroll_run_id=payroll_run.id, payment_method="TRANSFER")
    )
    assert paid.success
    assert payroll_repository.get_run(payroll_run.id).status == PayrollRunStatus.PAID
    assert len(paid_events) == 1
    assert paid_events[0].payload["payroll_run_id"] == payroll_run.id
    assert paid_events[0].payload["employee_ids"] == [employee.id]

    idempotent = PayPayrollRunUseCase(payroll_repository, payment_repository, event_bus=bus, permission_checker=checker).execute(
        PayPayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p003", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u003", payroll_run_id=payroll_run.id, payment_method="TRANSFER")
    )
    assert idempotent.success
    assert len(paid_events) == 1
    assert PayrollQueryService(conn).list_payments(payroll_run_id=payroll_run.id)[0].operation_id == "01900000-0000-7000-8000-00000000p003"

    with pytest.raises(PayrollAlreadyPaidError):
        PayPayrollRunUseCase(payroll_repository, payment_repository, event_bus=bus, permission_checker=checker).execute(
            PayPayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p004", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u003", payroll_run_id=payroll_run.id, payment_method="TRANSFER")
        )
    assert len(PayrollQueryService(conn).list_payments(payroll_run_id=payroll_run.id)) == 1


def test_payroll_cannot_pay_without_authorization_and_can_cancel_before_payment() -> None:
    conn, employee, payroll_repository, payment_repository = _setup()
    checker = lambda _user_id, permission: permission in {"hr.payroll.generate", "hr.payroll.pay", "hr.payroll.cancel"}
    generated = GeneratePayrollRunUseCase(payroll_repository, SQLiteEmployeeRepository(conn), permission_checker=checker).execute(
        _generate_command(employee, "01900000-0000-7000-8000-00000000p010")
    )
    payroll_run_id = generated.entity_id or ""
    with pytest.raises(PayrollNotAuthorizedError):
        PayPayrollRunUseCase(payroll_repository, payment_repository, permission_checker=checker).execute(
            PayPayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p011", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u003", payroll_run_id=payroll_run_id)
        )
    cancelled = CancelPayrollRunUseCase(payroll_repository, permission_checker=checker).execute(
        CancelPayrollRunCommand(operation_id="01900000-0000-7000-8000-00000000p012", branch_id=employee.branch_id, user_id="01900000-0000-7000-8000-00000000u004", payroll_run_id=payroll_run_id, reason="Periodo incorrecto")
    )
    assert cancelled.success
    assert payroll_repository.get_run(payroll_run_id).status == PayrollRunStatus.CANCELLED
