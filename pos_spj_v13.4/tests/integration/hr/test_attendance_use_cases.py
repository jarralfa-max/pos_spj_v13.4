"""FASE 4 — attendance: manual entry/exit, idempotency, incidents, adjustments."""

from datetime import date, datetime, timezone

import pytest

from backend.application.use_cases.hr.attendance_use_cases import (
    ApproveAttendanceAdjustmentUseCase,
    RegisterAttendancePunchUseCase,
    RegisterManualAttendanceUseCase,
    RequestAttendanceAdjustmentUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.domain.hr.enums import AttendanceSource, PunchType, WorkdayStatus
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH = new_uuid()


def _employee(conn, code="EMP-1", active=True):
    result = CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=code, first_name="Ana",
        last_name="García", branch_id=BRANCH, contract_type="PERMANENT",
        payment_frequency="SEMIMONTHLY", base_salary="15000.00", daily_salary="500.00",
        hire_date=date(2025, 1, 1), operation_id=new_uuid())
    return result.entity_id


def _at(hour, minute=0):
    return datetime(2026, 7, 16, hour, minute, tzinfo=timezone.utc)


class TestManualAttendance:
    def test_manual_entry_and_exit(self, hr_conn):
        emp = _employee(hr_conn)
        uc = RegisterManualAttendanceUseCase()
        entry = uc.execute(hr_conn, actor_user_id=new_uuid(), employee_id=emp,
                           branch_id=BRANCH, punch_type="ENTRY", occurred_at=_at(9),
                           reason="olvidó marcar", operation_id=new_uuid())
        assert entry.success and "entrada se registró" in entry.message
        exit_r = uc.execute(hr_conn, actor_user_id=new_uuid(), employee_id=emp,
                            branch_id=BRANCH, punch_type="EXIT", occurred_at=_at(17),
                            reason="olvidó marcar", operation_id=new_uuid())
        assert exit_r.success
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd.status is WorkdayStatus.COMPLETE and wd.worked_minutes == 480

    def test_manual_requires_reason(self, hr_conn):
        emp = _employee(hr_conn)
        result = RegisterManualAttendanceUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            punch_type="ENTRY", occurred_at=_at(9), reason="", operation_id=new_uuid())
        assert not result.success

    def test_inactive_employee_rejected(self, hr_conn):
        emp = _employee(hr_conn)
        with HRUnitOfWork(hr_conn) as uow:
            e = uow.employees.get(emp)
            e.deactivate(termination_date=date(2026, 1, 1), reason="baja")
            uow.employees.update(e)
        result = RegisterManualAttendanceUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH,
            punch_type="ENTRY", occurred_at=_at(9), reason="x", operation_id=new_uuid())
        assert not result.success and result.error_code == "EMPLOYEE_INACTIVE"


class TestIdempotency:
    def test_same_operation_id_no_duplicate(self, hr_conn):
        emp = _employee(hr_conn)
        uc = RegisterAttendancePunchUseCase()
        op = new_uuid()
        first = uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH,
                           punch_type=PunchType.ENTRY, occurred_at=_at(9),
                           source=AttendanceSource.MANUAL, operation_id=op)
        second = uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH,
                            punch_type=PunchType.ENTRY, occurred_at=_at(9),
                            source=AttendanceSource.MANUAL, operation_id=op)
        assert second.duplicated
        count = hr_conn.execute("SELECT COUNT(*) FROM attendance_punches").fetchone()[0]
        assert count == 1

    def test_duplicate_entry_not_created(self, hr_conn):
        emp = _employee(hr_conn)
        uc = RegisterAttendancePunchUseCase()
        uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.ENTRY,
                   occurred_at=_at(9), source=AttendanceSource.MANUAL, operation_id=new_uuid())
        second = uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH,
                            punch_type=PunchType.ENTRY, occurred_at=_at(9, 5),
                            source=AttendanceSource.MANUAL, operation_id=new_uuid())
        assert second.duplicated
        count = hr_conn.execute("SELECT COUNT(*) FROM attendance_punches").fetchone()[0]
        assert count == 1

    def test_cash_source_reference_idempotent(self, hr_conn):
        emp = _employee(hr_conn)
        uc = RegisterAttendancePunchUseCase()
        ref = new_uuid()
        uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.ENTRY,
                   occurred_at=_at(9), source=AttendanceSource.CASH_REGISTER,
                   operation_id=new_uuid(), source_reference_id=ref)
        second = uc.execute(hr_conn, employee_id=emp, branch_id=BRANCH,
                            punch_type=PunchType.ENTRY, occurred_at=_at(9),
                            source=AttendanceSource.CASH_REGISTER, operation_id=new_uuid(),
                            source_reference_id=ref)
        assert second.duplicated


class TestIncidents:
    def test_exit_without_entry_creates_incident(self, hr_conn):
        emp = _employee(hr_conn)
        result = RegisterAttendancePunchUseCase().execute(
            hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.EXIT,
            occurred_at=_at(17), source=AttendanceSource.MANUAL, operation_id=new_uuid())
        assert result.incident_created
        assert "incidencia" in result.result.message.lower()
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd.status is WorkdayStatus.INCIDENT
        events = hr_conn.execute(
            "SELECT COUNT(*) FROM hr_outbox WHERE event_name='ATTENDANCE_INCIDENT_CREATED'"
        ).fetchone()[0]
        assert events == 1


class TestAdjustments:
    def _workday_with_entry(self, hr_conn):
        emp = _employee(hr_conn)
        RegisterAttendancePunchUseCase().execute(
            hr_conn, employee_id=emp, branch_id=BRANCH, punch_type=PunchType.ENTRY,
            occurred_at=_at(9), source=AttendanceSource.MANUAL, operation_id=new_uuid())
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        return emp, wd.id

    def test_request_and_approve_adjustment(self, hr_conn):
        emp, workday_id = self._workday_with_entry(hr_conn)
        req = RequestAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), workday_id=workday_id,
            field_name="first_entry_at", requested_value="2026-07-16T08:30:00+00:00",
            reason="marcó tarde por error", operation_id=new_uuid())
        assert req.success
        approve = ApproveAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), adjustment_id=req.entity_id,
            operation_id=new_uuid(), approve=True)
        assert approve.success
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.get_workday(workday_id)
        assert wd.status is WorkdayStatus.ADJUSTED

    def test_reject_adjustment(self, hr_conn):
        emp, workday_id = self._workday_with_entry(hr_conn)
        req = RequestAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), workday_id=workday_id,
            field_name="first_entry_at", requested_value="2026-07-16T08:30:00+00:00",
            reason="test", operation_id=new_uuid())
        result = ApproveAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), adjustment_id=req.entity_id,
            operation_id=new_uuid(), approve=False)
        assert result.success
        with HRUnitOfWork(hr_conn) as uow:
            adj = uow.adjustments.get(req.entity_id)
        from backend.domain.hr.enums import AdjustmentStatus
        assert adj.status is AdjustmentStatus.REJECTED

    def test_original_punch_not_mutated(self, hr_conn):
        """La marcación original es inmutable; el ajuste solo cambia la jornada."""
        emp, workday_id = self._workday_with_entry(hr_conn)
        original = hr_conn.execute(
            "SELECT occurred_at FROM attendance_punches WHERE punch_type='ENTRY'").fetchone()[0]
        req = RequestAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), workday_id=workday_id,
            field_name="first_entry_at", requested_value="2026-07-16T08:30:00+00:00",
            reason="x", operation_id=new_uuid())
        ApproveAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), adjustment_id=req.entity_id,
            operation_id=new_uuid(), approve=True)
        after = hr_conn.execute(
            "SELECT occurred_at FROM attendance_punches WHERE punch_type='ENTRY'").fetchone()[0]
        assert original == after  # punch never overwritten
