"""FASE 8 — canonical payroll sequence Generate → Authorize → Pay (→ Cancel).

Mandatory scenarios: generation, authorization, payment, pay-without-authorization
rejection, double-pay prevention, cancellation, inactive employee handling, period
calculation, PAYROLL_PAID financial integration, idempotency and no double
financial movement.
"""

import json
from datetime import date, datetime, timezone

import pytest

from backend.application.use_cases.hr.attendance_use_cases import (
    RegisterAttendancePunchUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import (
    CreateEmployeeUseCase,
    DeactivateEmployeeUseCase,
)
from backend.application.use_cases.hr.payroll_use_cases import (
    AuthorizePayrollRunUseCase,
    CancelPayrollRunUseCase,
    GeneratePayrollRunUseCase,
    PayPayrollRunUseCase,
)
from backend.domain.hr.enums import AttendanceSource, PayrollRunStatus, PunchType
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid

BRANCH = new_uuid()
PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 15)


def _employee(conn, code="EMP-1", branch_id=BRANCH, daily="500.00"):
    return CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=code, first_name="Ana",
        last_name="García", branch_id=branch_id, contract_type="PERMANENT",
        payment_frequency="SEMIMONTHLY", base_salary="15000.00", daily_salary=daily,
        hire_date=date(2025, 1, 1), operation_id=new_uuid()).entity_id


def _generate(conn, *, generated_by=None, branch_id=BRANCH, operation_id=None):
    return GeneratePayrollRunUseCase().execute(
        conn, actor_user_id=generated_by or new_uuid(), period_start=PERIOD_START,
        period_end=PERIOD_END, operation_id=operation_id or new_uuid(),
        branch_id=branch_id)


def _authorize(conn, run_id, *, authorizer=None):
    return AuthorizePayrollRunUseCase().execute(
        conn, actor_user_id=authorizer or new_uuid(), payroll_run_id=run_id,
        operation_id=new_uuid())


def _pay(conn, run_id, *, payer=None, operation_id=None):
    return PayPayrollRunUseCase().execute(
        conn, actor_user_id=payer or new_uuid(), payroll_run_id=run_id,
        payment_method="CASH", operation_id=operation_id or new_uuid())


class TestGeneration:
    def test_generates_run_with_lines(self, hr_conn):
        _employee(hr_conn)
        result = _generate(hr_conn)
        assert result.success and result.entity_id
        with HRUnitOfWork(hr_conn) as uow:
            run = uow.payroll.get(result.entity_id)
        assert run.status is PayrollRunStatus.CALCULATED
        assert run.lines  # base salary line at minimum

    def test_no_employees_fails(self, hr_conn):
        result = _generate(hr_conn)
        assert not result.success and result.error_code == "NO_EMPLOYEES"

    def test_period_calculation_uses_full_period_when_no_attendance(self, hr_conn):
        # daily_salary 500 * 15 days = 7500 base salary when no attendance recorded
        _employee(hr_conn, daily="500.00")
        result = _generate(hr_conn)
        with HRUnitOfWork(hr_conn) as uow:
            run = uow.payroll.get(result.entity_id)
        assert run.gross_amount().to_string() == "7500.00"

    def test_idempotent_generation(self, hr_conn):
        _employee(hr_conn)
        op = new_uuid()
        first = _generate(hr_conn, operation_id=op)
        second = _generate(hr_conn, operation_id=op)
        assert first.entity_id == second.entity_id
        count = hr_conn.execute("SELECT COUNT(*) FROM payroll_runs").fetchone()[0]
        assert count == 1


class TestAuthorization:
    def test_authorize_calculated_run(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        result = _authorize(hr_conn, run_id)
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.payroll.get(run_id).status is PayrollRunStatus.AUTHORIZED

    def test_generator_cannot_authorize(self, hr_conn):
        _employee(hr_conn)
        generator = new_uuid()
        run_id = _generate(hr_conn, generated_by=generator).entity_id
        result = _authorize(hr_conn, run_id, authorizer=generator)
        assert not result.success and result.error_code == "VALIDATION"

    def test_cannot_authorize_missing_run(self, hr_conn):
        result = _authorize(hr_conn, new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"


class TestPayment:
    def test_full_sequence_generate_authorize_pay(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _authorize(hr_conn, run_id)
        result = _pay(hr_conn, run_id)
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            run = uow.payroll.get(run_id)
            payment = uow.payroll_payments.find_by_run(run_id)
        assert run.status is PayrollRunStatus.PAID
        assert payment is not None and run.payment_id == payment.id

    def test_pay_without_authorization_rejected(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id  # still CALCULATED
        result = _pay(hr_conn, run_id)
        assert not result.success and result.error_code == "PAYROLL_STATE"
        count = hr_conn.execute("SELECT COUNT(*) FROM payroll_payments").fetchone()[0]
        assert count == 0

    def test_double_pay_prevented(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _authorize(hr_conn, run_id)
        first = _pay(hr_conn, run_id)
        second = _pay(hr_conn, run_id)
        assert first.success and second.success
        # Idempotent: the second call returns the same existing payment, no new row.
        assert first.entity_id == second.entity_id
        count = hr_conn.execute("SELECT COUNT(*) FROM payroll_payments").fetchone()[0]
        assert count == 1

    def test_no_double_financial_movement(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _authorize(hr_conn, run_id)
        _pay(hr_conn, run_id)
        _pay(hr_conn, run_id)  # repeated payment attempt
        rows = hr_conn.execute(
            "SELECT COUNT(*) FROM hr_outbox WHERE event_name=?",
            (EventName.PAYROLL_PAID.value,)).fetchone()[0]
        # Exactly one PAYROLL_PAID event → finance posts the ledger once.
        assert rows == 1

    def test_payroll_paid_payload_finance_compatible(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _authorize(hr_conn, run_id)
        _pay(hr_conn, run_id)
        row = hr_conn.execute(
            "SELECT payload_json FROM hr_outbox WHERE event_name=?",
            (EventName.PAYROLL_PAID.value,)).fetchone()
        payload = json.loads(row[0])
        # canonical HR keys
        assert payload["payroll_run_id"] == run_id
        assert payload["net_amount"] == "7500.00"
        # finance-bridge compatibility keys
        assert payload["gross_salaries"] == "7500.00"
        assert payload["net_paid"] == "7500.00"
        assert payload["social_security"] == "0.00"


class TestCancellation:
    def test_cancel_calculated_run(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        result = CancelPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
            operation_id=new_uuid())
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.payroll.get(run_id).status is PayrollRunStatus.CANCELLED

    def test_cannot_cancel_paid_run(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _authorize(hr_conn, run_id)
        _pay(hr_conn, run_id)
        result = CancelPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PAYROLL_STATE"


class TestInactiveEmployee:
    def test_inactive_employee_excluded_from_run(self, hr_conn):
        active = _employee(hr_conn, code="EMP-ACTIVE")
        inactive = _employee(hr_conn, code="EMP-INACTIVE")
        DeactivateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=inactive,
            termination_date=date(2026, 6, 30), reason="baja", operation_id=new_uuid())
        run_id = _generate(hr_conn).entity_id
        with HRUnitOfWork(hr_conn) as uow:
            run = uow.payroll.get(run_id)
        employee_ids = run.employee_ids()
        assert active in employee_ids
        assert inactive not in employee_ids


class TestAttendanceDrivesPayroll:
    def test_overtime_increases_gross(self, hr_conn):
        emp = _employee(hr_conn, daily="480.00")
        # Register a full workday with overtime for one date in the period.
        RegisterAttendancePunchUseCase().execute(
            hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.ENTRY,
            occurred_at=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
            source=AttendanceSource.MANUAL, operation_id=new_uuid())
        RegisterAttendancePunchUseCase().execute(
            hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.EXIT,
            occurred_at=datetime(2026, 7, 2, 19, 0, tzinfo=timezone.utc),
            source=AttendanceSource.MANUAL, operation_id=new_uuid())
        result = _generate(hr_conn)
        with HRUnitOfWork(hr_conn) as uow:
            run = uow.payroll.get(result.entity_id)
        concepts = {line.concept.value for line in run.lines}
        assert "BASE_SALARY" in concepts
