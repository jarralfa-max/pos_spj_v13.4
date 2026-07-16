"""FASES 6-7 — work shifts assignment + leave request/approve/reject/cancel."""

from datetime import date, datetime, time, timezone

import pytest

from backend.application.use_cases.hr.attendance_use_cases import (
    RegisterAttendancePunchUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.application.use_cases.hr.leave_use_cases import (
    ApproveLeaveUseCase,
    CancelLeaveUseCase,
    RequestLeaveUseCase,
)
from backend.application.use_cases.hr.shift_use_cases import (
    AssignShiftUseCase,
    CreateShiftUseCase,
)
from backend.domain.hr.enums import AttendanceSource, LeaveStatus, PunchType
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH = new_uuid()


def _employee(conn, code="EMP-1"):
    return CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=code, first_name="Ana",
        last_name="García", branch_id=BRANCH, contract_type="PERMANENT",
        payment_frequency="SEMIMONTHLY", base_salary="15000.00", daily_salary="500.00",
        hire_date=date(2025, 1, 1), operation_id=new_uuid()).entity_id


class TestShifts:
    def test_create_and_assign_shift(self, hr_conn):
        emp = _employee(hr_conn)
        shift = CreateShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), name="Matutino",
            start_time=time(9, 0), end_time=time(17, 0), late_tolerance_minutes=10)
        assert shift.success
        assign = AssignShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp,
            work_shift_id=shift.entity_id, effective_from=date(2026, 7, 1),
            weekdays=(0, 1, 2, 3, 4))
        assert assign.success
        with HRUnitOfWork(hr_conn) as uow:
            found = uow.shifts.find_assignment_for(emp, date(2026, 7, 16))  # Thursday
        assert found is not None and found.work_shift_id == shift.entity_id

    def test_assignment_respects_weekdays(self, hr_conn):
        emp = _employee(hr_conn)
        shift = CreateShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), name="LunViernes",
            start_time=time(9), end_time=time(17))
        AssignShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp,
            work_shift_id=shift.entity_id, effective_from=date(2026, 7, 1),
            weekdays=(0, 1, 2, 3, 4))
        with HRUnitOfWork(hr_conn) as uow:
            sunday = uow.shifts.find_assignment_for(emp, date(2026, 7, 19))  # Sunday
        assert sunday is None

    def test_shift_drives_late_calculation(self, hr_conn):
        emp = _employee(hr_conn)
        shift = CreateShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), name="M", start_time=time(9),
            end_time=time(17), late_tolerance_minutes=5)
        AssignShiftUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp,
            work_shift_id=shift.entity_id, effective_from=date(2026, 7, 1),
            weekdays=(0, 1, 2, 3, 4))
        # entry at 09:20 → 20 late minutes (beyond 5 tolerance)
        RegisterAttendancePunchUseCase().execute(
            hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.ENTRY,
            occurred_at=datetime(2026, 7, 16, 9, 20, tzinfo=timezone.utc),
            source=AttendanceSource.MANUAL, operation_id=new_uuid())
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd.late_minutes == 20


class TestLeave:
    def test_request_and_approve(self, hr_conn):
        emp = _employee(hr_conn)
        req = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3), reason="viaje", operation_id=new_uuid())
        assert req.success and req.entity_id
        approve = ApproveLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), leave_id=req.entity_id,
            operation_id=new_uuid(), approve=True)
        assert approve.success
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.leaves.get(req.entity_id).status is LeaveStatus.APPROVED

    def test_overlap_rejected(self, hr_conn):
        emp = _employee(hr_conn)
        RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5), reason="x", operation_id=new_uuid())
        overlap = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 4),
            end_date=date(2026, 8, 8), reason="y", operation_id=new_uuid())
        assert not overlap.success and overlap.error_code == "VALIDATION"

    def test_insufficient_balance_rejected(self, hr_conn):
        emp = _employee(hr_conn)
        result = RequestLeaveUseCase(annual_vacation_days=5).execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 20), reason="largo", operation_id=new_uuid())
        assert not result.success

    def test_reject_and_cancel(self, hr_conn):
        emp = _employee(hr_conn)
        req = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="PAID_LEAVE", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1), reason="trámite", operation_id=new_uuid())
        rejected = ApproveLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), leave_id=req.entity_id,
            operation_id=new_uuid(), approve=False)
        assert rejected.success
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.leaves.get(req.entity_id).status is LeaveStatus.REJECTED

    def test_idempotent_request(self, hr_conn):
        emp = _employee(hr_conn)
        op = new_uuid()
        RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2), reason="x", operation_id=op)
        RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2), reason="x", operation_id=op)
        count = hr_conn.execute("SELECT COUNT(*) FROM leave_requests").fetchone()[0]
        assert count == 1

    def test_inactive_employee_cannot_request(self, hr_conn):
        emp = _employee(hr_conn)
        with HRUnitOfWork(hr_conn) as uow:
            e = uow.employees.get(emp)
            e.deactivate(termination_date=date(2026, 1, 1), reason="baja")
            uow.employees.update(e)
        result = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            leave_type="VACATION", start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2), reason="x", operation_id=new_uuid())
        assert not result.success and result.error_code == "EMPLOYEE_INACTIVE"
