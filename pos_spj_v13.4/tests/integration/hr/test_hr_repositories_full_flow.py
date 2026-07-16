from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, time
from decimal import Decimal

from backend.application.queries.attendance_query_service import AttendanceQueryService
from backend.application.queries.leave_query_service import LeaveQueryService
from backend.application.queries.payroll_query_service import PayrollQueryService
from backend.domain.hr.entities import (
    AttendanceAdjustment,
    AttendancePunch,
    AttendanceWorkday,
    Department,
    Employee,
    LeaveRequest,
    PayrollConcept,
    PayrollLine,
    PayrollPayment,
    PayrollRun,
    Position,
    ShiftAssignment,
    WorkShift,
)
from backend.domain.hr.enums import (
    AttendanceSource,
    ContractType,
    LeaveStatus,
    LeaveType,
    PaymentFrequency,
    PayrollConceptCode,
    PayrollRunStatus,
    PunchType,
    WorkdayStatus,
)
from backend.infrastructure.db.repositories.attendance_adjustment_repository import SQLiteAttendanceAdjustmentRepository
from backend.infrastructure.db.repositories.attendance_repository import SQLiteAttendanceRepository
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.employee_repository import SQLiteEmployeeRepository
from backend.infrastructure.db.repositories.leave_repository import SQLiteLeaveRepository
from backend.infrastructure.db.repositories.payroll_payment_repository import SQLitePayrollPaymentRepository
from backend.infrastructure.db.repositories.payroll_repository import SQLitePayrollRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.repositories.work_shift_repository import SQLiteWorkShiftRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema


def _seed_employee(conn: sqlite3.Connection) -> Employee:
    department = Department(name="Operaciones", branch_id="01900000-0000-7000-8000-000000000001")
    position = Position(name="Cajera", department_id=department.id)
    employee = Employee(
        employee_code="EMP-002",
        first_name="Beatriz",
        last_name="López",
        branch_id=department.branch_id,
        department_id=department.id,
        position_id=position.id,
        contract_type=ContractType.FULL_TIME,
        payment_frequency=PaymentFrequency.WEEKLY,
        base_salary=Decimal("1400"),
        daily_salary=Decimal("280"),
        hire_date=date(2026, 1, 1),
    )
    SQLiteDepartmentRepository(conn).save(department)
    SQLitePositionRepository(conn).save(position)
    SQLiteEmployeeRepository(conn).save(employee)
    return employee


def test_attendance_shift_leave_and_payroll_repositories_are_queryable_and_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    employee = _seed_employee(conn)
    branch_id = employee.branch_id
    now = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

    shift = WorkShift(
        name="Matutino",
        start_time=time(8, 0),
        end_time=time(16, 0),
        crosses_midnight=False,
        break_minutes=30,
        late_tolerance_minutes=10,
        branch_id=branch_id,
    )
    assignment = ShiftAssignment(
        employee_id=employee.id,
        work_shift_id=shift.id,
        effective_from=date(2026, 1, 1),
        weekdays="1,2,3,4,5",
        branch_id=branch_id,
    )
    shifts = SQLiteWorkShiftRepository(conn)
    shifts.save(shift)
    shifts.assign(assignment)

    attendance = SQLiteAttendanceRepository(conn)
    entry = AttendancePunch(
        employee_id=employee.id,
        branch_id=branch_id,
        punch_type=PunchType.ENTRY,
        occurred_at=now,
        timezone="UTC",
        source=AttendanceSource.MANUAL,
        operation_id="01900000-0000-7000-8000-00000000aa01",
        registered_by_user_id="01900000-0000-7000-8000-00000000bb01",
    )
    attendance.add_punch(entry)
    workday = AttendanceWorkday(
        employee_id=employee.id,
        branch_id=branch_id,
        work_date=date(2026, 1, 5),
        scheduled_shift_id=shift.id,
        first_entry_at=now,
        worked_minutes=480,
        late_minutes=0,
        overtime_minutes=30,
        status=WorkdayStatus.MISSING_EXIT,
    )
    attendance.save_workday(workday)
    SQLiteAttendanceAdjustmentRepository(conn).save(
        AttendanceAdjustment(
            original_punch_id=entry.id,
            requested_value=now,
            previous_value=now,
            reason="Corrección documentada",
            requested_by_user_id="01900000-0000-7000-8000-00000000bb01",
        )
    )

    leave = LeaveRequest(
        employee_id=employee.id,
        branch_id=branch_id,
        leave_type=LeaveType.VACATION,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        requested_days=Decimal("2"),
        reason="Vacaciones programadas",
        requested_by_user_id="01900000-0000-7000-8000-00000000bb01",
        operation_id="01900000-0000-7000-8000-00000000cc01",
        status=LeaveStatus.PENDING,
    )
    leave_repo = SQLiteLeaveRepository(conn)
    leave_repo.save(leave)
    leave_repo.save(leave)

    payroll = SQLitePayrollRepository(conn)
    run = PayrollRun(
        branch_id=branch_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 7),
        operation_id="01900000-0000-7000-8000-00000000dd01",
        status=PayrollRunStatus.AUTHORIZED,
        gross_amount=Decimal("1400"),
        deductions_amount=Decimal("100"),
        net_amount=Decimal("1300"),
    )
    payroll.save_run(run)
    line = PayrollLine(
        payroll_run_id=run.id,
        employee_id=employee.id,
        gross_amount=Decimal("1400"),
        deductions_amount=Decimal("100"),
        net_amount=Decimal("1300"),
    )
    payroll.save_line(line)
    payroll.save_concept(
        PayrollConcept(
            payroll_line_id=line.id,
            concept_code=PayrollConceptCode.BASE_SALARY,
            amount=Decimal("1400"),
        )
    )
    payment = PayrollPayment(
        payroll_run_id=run.id,
        branch_id=branch_id,
        payment_method="TRANSFER",
        net_amount=Decimal("1300"),
        operation_id="01900000-0000-7000-8000-00000000ee01",
        paid_by_user_id="01900000-0000-7000-8000-00000000bb01",
    )
    payments = SQLitePayrollPaymentRepository(conn)
    payments.save(payment)
    payments.save(payment)

    workdays = AttendanceQueryService(conn).list_workdays(branch_id=branch_id)
    assert len(workdays) == 1
    assert workdays[0].employee_id == employee.id
    assert workdays[0].status == WorkdayStatus.MISSING_EXIT.value

    pending_leave = LeaveQueryService(conn).list_pending()
    assert [item.id for item in pending_leave] == [leave.id]
    assert conn.execute("SELECT COUNT(*) FROM leave_requests").fetchone()[0] == 1

    payroll_runs = PayrollQueryService(conn).list_runs()
    assert [item.id for item in payroll_runs] == [run.id]
    assert payroll_runs[0].net_amount == Decimal("1300")
    assert conn.execute("SELECT COUNT(*) FROM payroll_payments").fetchone()[0] == 1
