"""FASE 2 — HR repositories + query services roundtrip over temporary SQLite."""

from datetime import date, datetime, time, timezone

import pytest

from backend.application.queries.hr.hr_query_services import (
    AttendanceQueryService,
    EmployeeQueryService,
    HRDashboardQueryService,
    PayrollQueryService,
)
from backend.domain.hr.entities import (
    AttendancePunch,
    AttendanceWorkday,
    Employee,
    LeaveRequest,
    PayrollLine,
    PayrollRun,
    WorkShift,
)
from backend.domain.hr.enums import (
    AttendanceSource,
    ContractType,
    LeaveType,
    PaymentFrequency,
    PayrollConcept,
    PunchType,
)
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH = new_uuid()


def _employee(daily="500.00", code="EMP-001", branch=BRANCH):
    return Employee.create(code, "Ana", "García", branch, ContractType.PERMANENT,
                           PaymentFrequency.SEMIMONTHLY, Money.from_string("15000.00"),
                           Money.from_string(daily), date(2025, 1, 1))


class TestEmployeeRepository:
    def test_save_and_get_roundtrip(self, hr_conn):
        emp = _employee()
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.save(emp)
        with HRUnitOfWork(hr_conn) as uow:
            stored = uow.employees.get(emp.id)
        assert stored is not None
        assert stored.employee_code == "EMP-001"
        assert stored.base_salary.to_string() == "15000.00"
        assert stored.daily_salary.to_string() == "500.00"

    def test_get_by_code(self, hr_conn):
        emp = _employee()
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.save(emp)
            assert uow.employees.get_by_code("EMP-001").id == emp.id

    def test_user_employee_link(self, hr_conn):
        emp = _employee()
        user_id = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'ana')", (user_id,))
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.save(emp)
            uow.employees.link_user(user_id, emp.id)
        with HRUnitOfWork(hr_conn) as uow:
            linked = uow.employees.get_by_user_id(user_id)
        assert linked is not None and linked.id == emp.id

    def test_update_deactivates(self, hr_conn):
        emp = _employee()
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.save(emp)
        emp.deactivate(termination_date=date(2026, 7, 16), reason="renuncia")
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.update(emp)
        with HRUnitOfWork(hr_conn) as uow:
            stored = uow.employees.get(emp.id)
        assert not stored.active and stored.termination_reason == "renuncia"

    def test_list_active_excludes_inactive(self, hr_conn):
        active = _employee(code="A1")
        inactive = _employee(code="A2")
        inactive.deactivate(termination_date=date(2026, 7, 16), reason="baja")
        with HRUnitOfWork(hr_conn) as uow:
            uow.employees.save(active)
            uow.employees.save(inactive)
        with HRUnitOfWork(hr_conn) as uow:
            listed = uow.employees.list_active()
        assert [e.employee_code for e in listed] == ["A1"]


class TestAttendanceRepository:
    def _emp(self, uow):
        emp = _employee()
        uow.employees.save(emp)
        return emp

    def test_punch_and_workday_roundtrip(self, hr_conn):
        with HRUnitOfWork(hr_conn) as uow:
            emp = self._emp(uow)
            wd = AttendanceWorkday.create(emp.id, BRANCH, date(2026, 7, 16))
            uow.attendance.save_workday(wd)
            punch = AttendancePunch.create(
                emp.id, BRANCH, PunchType.ENTRY,
                datetime(2026, 7, 16, 9, tzinfo=timezone.utc),
                AttendanceSource.MANUAL, new_uuid())
            uow.attendance.save_punch(punch, workday_id=wd.id)
        with HRUnitOfWork(hr_conn) as uow:
            punches = uow.attendance.list_punches_for_workday(wd.id)
            found = uow.attendance.find_workday(emp.id, date(2026, 7, 16))
        assert len(punches) == 1 and punches[0].punch_type is PunchType.ENTRY
        assert found is not None

    def test_find_punch_by_operation_id(self, hr_conn):
        with HRUnitOfWork(hr_conn) as uow:
            emp = self._emp(uow)
            op = new_uuid()
            punch = AttendancePunch.create(
                emp.id, BRANCH, PunchType.ENTRY,
                datetime(2026, 7, 16, 9, tzinfo=timezone.utc),
                AttendanceSource.CASH_REGISTER, op)
            uow.attendance.save_punch(punch)
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.attendance.find_punch_by_operation_id(op).id == punch.id


class TestPayrollRepository:
    def test_run_with_lines_roundtrip(self, hr_conn):
        with HRUnitOfWork(hr_conn) as uow:
            emp = _employee()
            uow.employees.save(emp)
            run = PayrollRun.create(date(2026, 7, 1), date(2026, 7, 15), new_uuid(),
                                    generated_by_user_id=new_uuid())
            run.add_line(PayrollLine.create(run.id, emp.id, PayrollConcept.BASE_SALARY,
                                            Money.from_string("7500.00"), is_deduction=False))
            run.add_line(PayrollLine.create(run.id, emp.id, PayrollConcept.LATE_DEDUCTION,
                                            Money.from_string("100.00"), is_deduction=True))
            run.mark_calculated()
            uow.payroll.save(run)
        with HRUnitOfWork(hr_conn) as uow:
            stored = uow.payroll.get(run.id)
        assert len(stored.lines) == 2
        assert stored.net_amount().to_string() == "7400.00"


class TestQueryServices:
    def _seed(self, hr_conn):
        with HRUnitOfWork(hr_conn) as uow:
            emp = _employee()
            uow.employees.save(emp)
            wd = AttendanceWorkday.create(emp.id, BRANCH, date(2026, 7, 16))
            wd.first_entry_at = datetime(2026, 7, 16, 9, tzinfo=timezone.utc)
            wd.last_exit_at = datetime(2026, 7, 16, 17, tzinfo=timezone.utc)
            wd.worked_minutes = 480
            from backend.domain.hr.enums import WorkdayStatus
            wd.status = WorkdayStatus.COMPLETE
            uow.attendance.save_workday(wd)
        return emp

    def test_employee_query_search(self, hr_conn):
        self._seed(hr_conn)
        rows = EmployeeQueryService(hr_conn).list_employees(search="Gar")
        assert len(rows) == 1 and rows[0]["employee_code"] == "EMP-001"
        assert "id" in rows[0]  # UUID present in data, UI decides visibility

    def test_attendance_query_lists_workday(self, hr_conn):
        self._seed(hr_conn)
        rows = AttendanceQueryService(hr_conn).list_workdays(work_date="2026-07-16")
        assert len(rows) == 1 and rows[0]["employee_name"] == "Ana García"

    def test_dashboard_overview(self, hr_conn):
        self._seed(hr_conn)
        overview = HRDashboardQueryService(hr_conn).overview(work_date="2026-07-16")
        assert overview["active_employees"] == 1
        assert overview["present_today"] == 1
        assert overview["absences_today"] == 0
