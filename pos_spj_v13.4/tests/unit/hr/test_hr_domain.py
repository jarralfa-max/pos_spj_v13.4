"""FASE 1 — HR domain: identity, immutability, attendance, leave, payroll rules."""

import re
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

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
    LeaveStatus,
    LeaveType,
    PaymentFrequency,
    PayrollConcept,
    PayrollRunStatus,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.exceptions import (
    HRDomainError,
    InvalidLeaveDatesError,
    PayrollAlreadyPaidError,
    PayrollNotAuthorizedError,
)
from backend.domain.hr.policies.attendance_policy import AttendancePolicy
from backend.domain.hr.policies.leave_policy import LeavePolicy
from backend.domain.hr.services.payroll_calculator import (
    EmployeePayrollInput,
    PayrollCalculator,
)
from backend.domain.hr.services.workday_builder import WorkdayBuilder
from backend.domain.hr.value_objects import Money, PhoneE164
from backend.shared.ids import new_uuid

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _employee(daily="500.00"):
    return Employee.create(
        "EMP-001", "Ana", "García", new_uuid(), ContractType.PERMANENT,
        PaymentFrequency.SEMIMONTHLY, Money.from_string("15000.00"),
        Money.from_string(daily), date(2025, 1, 1),
    )


def _punch(employee_id, branch_id, ptype, hour):
    return AttendancePunch.create(
        employee_id, branch_id, ptype,
        datetime(2026, 7, 16, hour, 0, tzinfo=timezone.utc),
        AttendanceSource.MANUAL, new_uuid(),
    )


class TestValueObjects:
    def test_money_rejects_float(self):
        with pytest.raises(HRDomainError):
            Money(1.5)  # type: ignore[arg-type]

    def test_money_decimal_arithmetic(self):
        total = Money.from_string("0.1").add(Money.from_string("0.2"))
        assert total.amount == Decimal("0.30")

    def test_phone_e164_validation(self):
        assert str(PhoneE164("+525512345678")) == "+525512345678"
        with pytest.raises(HRDomainError):
            PhoneE164("5512345678")


class TestEmployee:
    def test_create_has_uuidv7_and_active(self):
        emp = _employee()
        assert UUID_RE.match(emp.id)
        assert emp.active and emp.full_name == "Ana García"

    def test_deactivate_requires_reason(self):
        emp = _employee()
        with pytest.raises(HRDomainError):
            emp.deactivate(termination_date=date(2026, 7, 16), reason="")
        emp.deactivate(termination_date=date(2026, 7, 16), reason="renuncia")
        with pytest.raises(Exception):
            emp.assert_active()


class TestAttendanceImmutability:
    def test_punch_is_frozen(self):
        punch = _punch(new_uuid(), new_uuid(), PunchType.ENTRY, 9)
        with pytest.raises(Exception):
            punch.occurred_at = datetime.now(timezone.utc)  # type: ignore[misc]

    def test_punch_uuidv7(self):
        punch = _punch(new_uuid(), new_uuid(), PunchType.ENTRY, 9)
        assert UUID_RE.match(punch.id)


class TestWorkdayBuilder:
    def test_entry_only_is_open(self):
        emp, branch = new_uuid(), new_uuid()
        wd = AttendanceWorkday.create(emp, branch, date(2026, 7, 16))
        entry = _punch(emp, branch, PunchType.ENTRY, 9)
        WorkdayBuilder().rebuild(wd, [entry])
        assert wd.status is WorkdayStatus.OPEN and wd.first_entry_at is not None

    def test_entry_and_exit_computes_worked_minutes(self):
        emp, branch = new_uuid(), new_uuid()
        wd = AttendanceWorkday.create(emp, branch, date(2026, 7, 16))
        WorkdayBuilder().rebuild(wd, [
            _punch(emp, branch, PunchType.ENTRY, 9),
            _punch(emp, branch, PunchType.EXIT, 17),
        ])
        assert wd.status is WorkdayStatus.COMPLETE
        assert wd.worked_minutes == 8 * 60

    def test_exit_without_entry_is_incident(self):
        emp, branch = new_uuid(), new_uuid()
        wd = AttendanceWorkday.create(emp, branch, date(2026, 7, 16))
        WorkdayBuilder().rebuild(wd, [_punch(emp, branch, PunchType.EXIT, 17)])
        assert wd.status is WorkdayStatus.INCIDENT

    def test_late_minutes_with_tolerance(self):
        shift = WorkShift.create("Matutino", time(9, 0), time(17, 0),
                                 late_tolerance_minutes=10)
        policy = AttendancePolicy()
        on_time = datetime(2026, 7, 16, 9, 8, tzinfo=timezone.utc)
        late = datetime(2026, 7, 16, 9, 25, tzinfo=timezone.utc)
        assert policy.late_minutes(on_time, shift) == 0
        assert policy.late_minutes(late, shift) == 25


class TestAttendancePolicy:
    def test_exit_without_open_entry_rejected(self):
        wd = AttendanceWorkday.create(new_uuid(), new_uuid(), date(2026, 7, 16))
        from backend.domain.hr.exceptions import AttendanceMissingEntryError
        with pytest.raises(AttendanceMissingEntryError):
            AttendancePolicy().enforce_exit(wd)

    def test_duplicate_entry_rejected(self):
        wd = AttendanceWorkday.create(new_uuid(), new_uuid(), date(2026, 7, 16))
        wd.first_entry_at = datetime(2026, 7, 16, 9, tzinfo=timezone.utc)
        from backend.domain.hr.exceptions import AttendanceAlreadyOpenError
        with pytest.raises(AttendanceAlreadyOpenError):
            AttendancePolicy().enforce_entry(wd)


class TestLeave:
    def test_end_before_start_rejected(self):
        with pytest.raises(InvalidLeaveDatesError):
            LeaveRequest.create(new_uuid(), new_uuid(), LeaveType.VACATION,
                                date(2026, 7, 10), date(2026, 7, 5), "viaje",
                                new_uuid(), new_uuid())

    def test_requested_days_inclusive(self):
        req = LeaveRequest.create(new_uuid(), new_uuid(), LeaveType.VACATION,
                                  date(2026, 7, 10), date(2026, 7, 12), "viaje",
                                  new_uuid(), new_uuid())
        assert req.requested_days == 3

    def test_overlap_detection(self):
        existing = LeaveRequest.create(new_uuid(), new_uuid(), LeaveType.VACATION,
                                       date(2026, 7, 10), date(2026, 7, 15), "x",
                                       new_uuid(), new_uuid())
        from backend.domain.hr.exceptions import LeaveOverlapError
        with pytest.raises(LeaveOverlapError):
            LeavePolicy().enforce_no_overlap(date(2026, 7, 14), date(2026, 7, 18),
                                             [existing])

    def test_balance_enforced_for_vacation(self):
        from backend.domain.hr.exceptions import InsufficientLeaveBalanceError
        with pytest.raises(InsufficientLeaveBalanceError):
            LeavePolicy().enforce_balance(LeaveType.VACATION, 10, 5)
        # sick leave doesn't consume vacation balance
        LeavePolicy().enforce_balance(LeaveType.SICK_LEAVE, 10, 0)


class TestPayrollRun:
    def _run_with_line(self, generated_by=None):
        run = PayrollRun.create(date(2026, 7, 1), date(2026, 7, 15), new_uuid(),
                                generated_by_user_id=generated_by)
        run.add_line(PayrollLine.create(run.id, new_uuid(), PayrollConcept.BASE_SALARY,
                                        Money.from_string("7500.00"), is_deduction=False))
        return run

    def test_net_gross_deductions(self):
        run = self._run_with_line()
        run.add_line(PayrollLine.create(run.id, run.lines[0].employee_id,
                                        PayrollConcept.LATE_DEDUCTION,
                                        Money.from_string("100.00"), is_deduction=True))
        assert run.gross_amount().to_string() == "7500.00"
        assert run.deductions_amount().to_string() == "100.00"
        assert run.net_amount().to_string() == "7400.00"

    def test_cannot_pay_without_authorization(self):
        run = self._run_with_line()
        run.mark_calculated()
        with pytest.raises(PayrollNotAuthorizedError):
            run.mark_paid(new_uuid())

    def test_segregation_generator_cannot_authorize(self):
        user = new_uuid()
        run = self._run_with_line(generated_by=user)
        run.mark_calculated()
        with pytest.raises(HRDomainError):
            run.authorize(user)

    def test_full_lifecycle_and_no_double_pay(self):
        run = self._run_with_line(generated_by=new_uuid())
        run.mark_calculated()
        run.authorize(new_uuid())
        run.mark_paid(new_uuid())
        assert run.status is PayrollRunStatus.PAID
        with pytest.raises(PayrollAlreadyPaidError):
            run.mark_paid(new_uuid())

    def test_paid_run_is_immutable(self):
        run = self._run_with_line(generated_by=new_uuid())
        run.mark_calculated()
        run.authorize(new_uuid())
        run.mark_paid(new_uuid())
        with pytest.raises(Exception):
            run.add_line(PayrollLine.create(run.id, new_uuid(),
                                            PayrollConcept.BONUS,
                                            Money.from_string("1.00"), is_deduction=False))


class TestPayrollCalculator:
    def test_builds_base_and_overtime_and_absence(self):
        emp = _employee(daily="480.00")
        item = EmployeePayrollInput(employee=emp, worked_days=15, overtime_minutes=60,
                                    absence_days=1)
        lines = PayrollCalculator().build_lines(new_uuid(), item)
        concepts = {l.concept for l in lines}
        assert PayrollConcept.BASE_SALARY in concepts
        assert PayrollConcept.OVERTIME in concepts
        assert PayrollConcept.ABSENCE_DEDUCTION in concepts
        base = next(l for l in lines if l.concept is PayrollConcept.BASE_SALARY)
        assert base.amount.to_string() == "7200.00"  # 480 * 15
