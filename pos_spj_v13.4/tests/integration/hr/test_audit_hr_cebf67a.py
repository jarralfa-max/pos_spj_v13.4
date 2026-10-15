"""Auditoría directa de RR. HH. (cebf67a) — un escenario por hallazgo.

Cada prueba reproduce el escenario del informe con clases reales sobre SQLite
con ``foreign_keys`` y verifica el contrato CORREGIDO (no el defecto).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.event_handlers.hr.cash_attendance_handlers import (
    CashShiftClosedAttendanceHandler,
    CashShiftOpenedAttendanceHandler,
    reprocess_pending_cash_attendance,
    wire_cash_attendance,
)
from backend.application.hr.session_authorization import HRSessionPermissionChecker
from backend.application.queries.hr.hr_query_services import (
    EmployeeQueryService,
    HRDashboardQueryService,
    PayrollQueryService,
)
from backend.application.use_cases.hr.attendance_use_cases import (
    ApproveAttendanceAdjustmentUseCase,
    RecalculateWorkdayUseCase,
    RegisterAttendancePunchUseCase,
    RegisterManualAttendanceUseCase,
    RequestAttendanceAdjustmentUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import (
    CreateEmployeeUseCase,
    DeactivateEmployeeUseCase,
    LinkEmployeeUserUseCase,
    UpdateEmployeeUseCase,
)
from backend.application.use_cases.hr.leave_use_cases import (
    ApproveLeaveUseCase,
    CancelLeaveUseCase,
    RequestLeaveUseCase,
)
from backend.application.use_cases.hr.payroll_use_cases import (
    AuthorizePayrollRunUseCase,
    CancelPayrollRunUseCase,
    GeneratePayrollRunUseCase,
    PayPayrollRunUseCase,
)
from backend.application.use_cases.hr.shift_use_cases import (
    AssignShiftUseCase,
    CreateShiftUseCase,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.domain.hr.entities import PayrollLine, PayrollRun
from backend.domain.hr.enums import (
    AttendanceIncidentType,
    AttendanceSource,
    PayrollConcept,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.exceptions import HRDomainError, PermissionDeniedError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.services.attendance_calculator import AttendanceCalculator
from backend.domain.hr.services.payroll_calculator import (
    EmployeePayrollInput,
    PayrollCalculator,
)
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH_A = new_uuid()
BRANCH_B = new_uuid()
CDMX = timezone(timedelta(hours=-6))
JULY_1, JULY_7 = date(2026, 7, 1), date(2026, 7, 7)
AFTER = date(2026, 7, 31)


def _local(day: date, hour: int, minute: int = 0) -> datetime:
    """Instante UTC equivalente a una hora local de la Ciudad de México."""
    return datetime.combine(day, time(hour, minute), tzinfo=CDMX).astimezone(timezone.utc)


def _employee(conn, *, code=None, branch=BRANCH_A, daily="300.00", hire=date(2025, 1, 1),
              contract="PERMANENT", link_user=None) -> str:
    result = CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=code or f"E-{new_uuid()[-6:]}",
        first_name="Ana", last_name="Pérez", branch_id=branch, contract_type=contract,
        payment_frequency="WEEKLY", base_salary="0.00", daily_salary=daily,
        hire_date=hire, operation_id=new_uuid(), link_user_id=link_user)
    assert result.success, result.message
    return result.entity_id


def _punch(conn, employee_id, kind, moment, *, branch=BRANCH_A, ref=None):
    return RegisterAttendancePunchUseCase().execute(
        conn, employee_id=employee_id, branch_id=branch, punch_type=kind,
        occurred_at=moment, source=AttendanceSource.MANUAL, operation_id=new_uuid(),
        source_reference_id=ref)


def _workday(conn, employee_id, day):
    with HRUnitOfWork(conn) as uow:
        return uow.attendance.find_workday(employee_id, day)


def _generate(conn, *, start=JULY_1, end=JULY_7, branch=BRANCH_A, op=None, actor=None):
    return GeneratePayrollRunUseCase().execute(
        conn, actor_user_id=actor or new_uuid(), period_start=start, period_end=end,
        operation_id=op or new_uuid(), branch_id=branch, today=AFTER)


def _run(conn, run_id) -> PayrollRun:
    with HRUnitOfWork(conn) as uow:
        return uow.payroll.get(run_id)


class _Session:
    def __init__(self, user_id, branch, permissions, *, assigned=()):
        self.user_id = user_id
        self.active_branch_id = branch
        self.assigned_branch_ids = frozenset(assigned)
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code):
        return code in self._permissions


# ── HR-01 / HR-02 / HR-20 / HR-21 — composición real y alcance ──────────────
class TestHR01Authorization:
    def test_policy_without_checker_denies(self):
        policy = AuthorizationPolicy.__new__(AuthorizationPolicy)
        policy._checker = None
        with pytest.raises(PermissionDeniedError):
            policy.require(new_uuid(), HRPermission.EMPLOYEE_CREATE)

    def test_production_composition_enforces_session_permissions(self, hr_conn):
        from frontend.desktop.modules.hr.hr_routes import build_hr_presenter
        user = new_uuid()
        viewer = _Session(user, BRANCH_A, {HRPermission.VIEW, HRPermission.EMPLOYEE_VIEW})
        ok, message = build_hr_presenter(hr_conn, viewer).create_employee(
            employee_code="X-1", first_name="A", last_name="B", contract_type="PERMANENT",
            payment_frequency="WEEKLY", base_salary="0", daily_salary="300",
            hire_date=date(2026, 1, 1))
        assert not ok and "RRHH.empleado.crear" in message
        ok, _ = build_hr_presenter(hr_conn, None).create_employee(
            employee_code="X-2", first_name="A", last_name="B", contract_type="PERMANENT",
            payment_frequency="WEEKLY", base_salary="0", daily_salary="300",
            hire_date=date(2026, 1, 1))
        assert not ok
        assert hr_conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0

    def test_view_without_pay_permission_cannot_pay(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        AuthorizePayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
        user = new_uuid()
        session = _Session(user, BRANCH_A, {HRPermission.VIEW, HRPermission.PAYROLL_VIEW})
        policy = AuthorizationPolicy(HRSessionPermissionChecker(session))
        with pytest.raises(PermissionDeniedError):
            PayPayrollRunUseCase(policy).execute(
                hr_conn, actor_user_id=user, payroll_run_id=run_id,
                payment_method="CASH", operation_id=new_uuid())

    def test_ui_create_employee_uses_session_branch(self, hr_conn):
        from frontend.desktop.modules.hr.hr_routes import build_hr_presenter
        user = new_uuid()
        session = _Session(user, BRANCH_A, {HRPermission.VIEW, HRPermission.EMPLOYEE_CREATE})
        ok, message = build_hr_presenter(hr_conn, session).create_employee(
            employee_code="UI-1", first_name="Ana", last_name="Pérez",
            contract_type="PERMANENT", payment_frequency="WEEKLY", base_salary="0",
            daily_salary="300", hire_date=date(2026, 1, 1))
        assert ok, message
        assert hr_conn.execute("SELECT branch_id FROM employees").fetchone()[0] == BRANCH_A

    def test_shift_options_build_from_rows(self, hr_conn):
        from frontend.desktop.modules.hr.hr_routes import build_hr_presenter
        CreateShiftUseCase().execute(hr_conn, actor_user_id=new_uuid(), name="Matutino",
                                     start_time=time(9), end_time=time(17))
        session = _Session(new_uuid(), BRANCH_A, {HRPermission.VIEW})
        options = build_hr_presenter(hr_conn, session).shift_options()
        assert [label for _, label in options] == ["Matutino"]


class TestHR02BranchScope:
    def test_other_branch_documents_are_not_listed_nor_mutable(self, hr_conn):
        from frontend.desktop.modules.hr.hr_routes import build_hr_presenter
        emp_b = _employee(hr_conn, branch=BRANCH_B)
        leave = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp_b, branch_id=BRANCH_B,
            leave_type="PAID_LEAVE", start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 3), reason="trámite", operation_id=new_uuid())
        _generate(hr_conn, branch=BRANCH_B)
        user = new_uuid()
        everything = {code for code in vars(HRPermission).values()
                      if isinstance(code, str) and "sucursales" not in code}
        session = _Session(user, BRANCH_A, everything)
        presenter = build_hr_presenter(hr_conn, session)
        assert presenter.leave_requests().rows == []
        assert presenter.payroll_runs().rows == []
        ok, message = presenter.resolve_leave(leave.entity_id, approve=True)
        assert not ok and "alcance" in message

    def test_assigned_branch_needs_scope_permission(self):
        user = new_uuid()
        session = _Session(user, BRANCH_A, {HRPermission.VIEW}, assigned=[BRANCH_B])
        checker = HRSessionPermissionChecker(session)
        assert checker.can_access_branch(user, BRANCH_A)
        assert not checker.can_access_branch(user, BRANCH_B)
        session._permissions.add(HRPermission.VIEW_ASSIGNED_BRANCHES)
        assert checker.can_access_branch(user, BRANCH_B)
        assert not checker.can_access_branch(user, "")          # corrida de todas


# ── HR-03 / HR-04 / HR-05 / HR-06 — integraciones ───────────────────────────
class _RecordingBus:
    def __init__(self):
        self.subscribed = {}

    def subscribe(self, event_name, handler, **_kwargs):
        self.subscribed.setdefault(event_name, []).append(handler)


class TestHR03HR05HR06CashAttendance:
    def test_cash_shift_events_have_consumers(self, hr_conn):
        bus = _RecordingBus()
        wire_cash_attendance(bus, hr_conn)
        assert bus.subscribed.get("CASH_SHIFT_OPENED")
        assert bus.subscribed.get("CASH_SHIFT_CLOSED")

    def test_canonical_cash_envelope_registers_the_cashier(self, hr_conn):
        cashier = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'caja')", (cashier,))
        employee_id = _employee(hr_conn, link_user=cashier)
        supervisor, shift_id = new_uuid(), new_uuid()
        opened = cash_event_payload(CashEvents.SHIFT_OPENED, operation_id=new_uuid(),
                                    entity_id=shift_id, branch_id=BRANCH_A,
                                    user_id=supervisor, cashier_user_id=cashier)
        opened["timestamp"] = "2026-07-01T15:00:00+00:00"      # 09:00 local
        closed = cash_event_payload(CashEvents.SHIFT_CLOSED, operation_id=new_uuid(),
                                    entity_id=shift_id, branch_id=BRANCH_A,
                                    user_id=supervisor, cashier_user_id=cashier,
                                    shift_id=shift_id, closed_at="2026-07-01T23:00:00+00:00")
        CashShiftOpenedAttendanceHandler(hr_conn).handle(opened)
        CashShiftClosedAttendanceHandler(hr_conn).handle(closed)
        CashShiftOpenedAttendanceHandler(hr_conn).handle(opened)       # reentrega
        punches = hr_conn.execute(
            "SELECT employee_id, source_reference_id, operation_id, occurred_at,"
            " registered_by_user_id FROM attendance_punches ORDER BY occurred_at").fetchall()
        assert len(punches) == 2
        assert {p[0] for p in punches} == {employee_id}
        assert {p[1] for p in punches} == {shift_id}
        assert len({p[2] for p in punches}) == 2 and all(p[2] for p in punches)
        assert punches[0][3] == "2026-07-01T15:00:00+00:00"
        assert {p[4] for p in punches} == {cashier}            # el cajero, no el supervisor
        assert _workday(hr_conn, employee_id, JULY_1).worked_minutes == 480

    def test_envelope_without_time_is_rejected_not_invented(self, hr_conn):
        payload = cash_event_payload(CashEvents.SHIFT_OPENED, operation_id=new_uuid(),
                                     entity_id=new_uuid(), branch_id=BRANCH_A,
                                     user_id=new_uuid(), cashier_user_id=new_uuid())
        payload.pop("timestamp")
        with pytest.raises(HRDomainError, match="hora"):
            CashShiftOpenedAttendanceHandler(hr_conn).handle(payload)

    def test_unlinked_cashier_is_held_and_applied_after_linking(self, hr_conn):
        cashier = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'nuevo')", (cashier,))
        employee_id = _employee(hr_conn)
        opened = cash_event_payload(CashEvents.SHIFT_OPENED, operation_id=new_uuid(),
                                    entity_id=new_uuid(), branch_id=BRANCH_A,
                                    user_id=cashier, cashier_user_id=cashier)
        CashShiftOpenedAttendanceHandler(hr_conn).handle(opened)
        assert hr_conn.execute("SELECT COUNT(*) FROM hr_processed_events").fetchone()[0] == 0
        result = LinkEmployeeUserUseCase(
            reprocess=lambda conn, user_id: reprocess_pending_cash_attendance(
                conn, user_id=user_id)).execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=employee_id, user_id=cashier,
            operation_id=new_uuid())
        assert result.success and result.data["reprocessed"] == 1
        reprocess_pending_cash_attendance(hr_conn)                       # otra vez: nada
        assert hr_conn.execute("SELECT COUNT(*) FROM attendance_punches").fetchone()[0] == 1
        assert hr_conn.execute("SELECT status FROM hr_inbox").fetchone()[0] == "PROCESSED"


class TestHR04PayrollEnvelope:
    def test_paid_event_carries_outbox_identity_date_and_currency(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        AuthorizePayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
        assert PayPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
            payment_method="BANK_TRANSFER", payment_reference="SPEI-1",
            operation_id=new_uuid()).success
        event_id, payload_json = hr_conn.execute(
            "SELECT event_id, payload_json FROM hr_outbox WHERE event_name='PAYROLL_PAID'"
        ).fetchone()
        payload = json.loads(payload_json)
        assert payload["event_id"] == event_id
        assert payload["occurred_at"] and payload["currency_code"] == "MXN"
        assert payload["payment_reference"] == "SPEI-1"
        assert sum(Decimal(a["net_amount"]) for a in payload["allocations"]) \
            == Decimal(payload["net_paid"])


# ── HR-07 / HR-08 / HR-09 / HR-12 — cálculo ─────────────────────────────────
class TestHR07HR08HR09Payroll:
    def test_one_complete_workday_does_not_change_salaried_formula(self, hr_conn):
        emp = _employee(hr_conn)
        before = _generate(hr_conn, op=new_uuid())
        CancelPayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                          payroll_run_id=before.entity_id,
                                          operation_id=new_uuid())
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 9))
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 17))
        after = _generate(hr_conn)
        assert before.data["net"] == after.data["net"] == "2100.00"

    def test_incident_only_period_blocks_authorization(self, hr_conn):
        emp = _employee(hr_conn)
        _punch(hr_conn, emp, PunchType.EXIT, _local(date(2026, 7, 2), 17))
        generated = _generate(hr_conn)
        assert generated.data["pending_attendance"] == 1
        result = AuthorizePayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=generated.entity_id,
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PENDING_ATTENDANCE"

    def test_approved_unpaid_leave_is_deducted(self, hr_conn):
        emp = _employee(hr_conn)
        leave = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH_A,
            leave_type="UNPAID_LEAVE", start_date=date(2026, 7, 2),
            end_date=date(2026, 7, 3), reason="asunto personal", operation_id=new_uuid())
        ApproveLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                      leave_id=leave.entity_id, operation_id=new_uuid())
        generated = _generate(hr_conn)
        assert generated.data["net"] == "1500.00"
        concepts = {line.concept for line in _run(hr_conn, generated.entity_id).lines}
        assert PayrollConcept.ABSENCE_DEDUCTION in concepts

    def test_future_hire_is_not_paid_for_an_earlier_period(self, hr_conn):
        _employee(hr_conn, hire=date(2026, 8, 1))
        result = _generate(hr_conn)
        assert not result.success and result.error_code == "NO_EMPLOYEES"

    def test_later_termination_keeps_historical_eligibility(self, hr_conn):
        emp = _employee(hr_conn)
        DeactivateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp,
            termination_date=date(2026, 9, 1), reason="renuncia", operation_id=new_uuid())
        assert _generate(hr_conn).data["net"] == "2100.00"

    def test_salary_change_does_not_rewrite_a_past_period(self, hr_conn):
        emp = _employee(hr_conn)
        assert UpdateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, operation_id=new_uuid(),
            daily_salary="600.00", salary_effective_from=date(2026, 8, 1)).success
        assert _generate(hr_conn).data["net"] == "2100.00"
        august = _generate(hr_conn, start=date(2026, 8, 1), end=date(2026, 8, 7))
        assert august.data["net"] == "4200.00"

    def test_overtime_rate_is_rounded_once(self):
        from backend.domain.hr.entities import Employee
        from backend.domain.hr.enums import ContractType, PaymentFrequency
        employee = Employee.create("E", "A", "B", BRANCH_A, ContractType.PERMANENT,
                                   PaymentFrequency.WEEKLY, Money.from_string("0"),
                                   Money.from_string("300"), date(2025, 1, 1))
        lines = PayrollCalculator().build_lines(
            new_uuid(), EmployeePayrollInput(employee=employee, worked_days=0,
                                             overtime_minutes=60))
        overtime = next(line for line in lines if line.concept is PayrollConcept.OVERTIME)
        assert overtime.amount.to_string() == "56.25"


# ── HR-10 / HR-11 / HR-27 — controles de pago ───────────────────────────────
class TestHR10HR11HR27PaymentControls:
    def test_overlapping_ordinary_run_is_rejected_until_cancelled(self, hr_conn):
        _employee(hr_conn)
        first = _generate(hr_conn)
        second = _generate(hr_conn, start=date(2026, 7, 5), end=date(2026, 7, 11))
        assert not second.success and second.error_code == "PAYROLL_OVERLAP"
        CancelPayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                          payroll_run_id=first.entity_id,
                                          operation_id=new_uuid())
        assert _generate(hr_conn).success

    def test_reused_operation_with_other_period_conflicts(self, hr_conn):
        _employee(hr_conn)
        op = new_uuid()
        assert _generate(hr_conn, op=op).success
        again = _generate(hr_conn, op=op, start=date(2026, 7, 8), end=date(2026, 7, 14))
        assert not again.success and again.error_code == "IDEMPOTENCY_CONFLICT"

    def _two_employee_run(self):
        run = PayrollRun.create(JULY_1, JULY_7, new_uuid(), branch_id=BRANCH_A,
                                generated_by_user_id=new_uuid())
        a, b = new_uuid(), new_uuid()
        run.add_line(PayrollLine.create(run.id, a, PayrollConcept.BASE_SALARY,
                                        Money.from_string("100"), is_deduction=False))
        run.add_line(PayrollLine.create(run.id, a, PayrollConcept.LATE_DEDUCTION,
                                        Money.from_string("246.40"), is_deduction=True))
        run.add_line(PayrollLine.create(run.id, b, PayrollConcept.BASE_SALARY,
                                        Money.from_string("2100"), is_deduction=False))
        run.mark_calculated()
        return run

    def test_negative_individual_net_blocks_authorization(self):
        run = self._two_employee_run()
        assert run.net_amount().is_positive()
        with pytest.raises(HRDomainError, match="neto negativo"):
            run.authorize(new_uuid())

    def test_authorized_amount_is_frozen(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        AuthorizePayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
        run = _run(hr_conn, run_id)
        with pytest.raises(HRDomainError):
            run.add_line(PayrollLine.create(run.id, run.lines[0].employee_id,
                                            PayrollConcept.BONUS, Money.from_string("100"),
                                            is_deduction=False))

    def test_payment_requires_method_and_reference(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        AuthorizePayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
        no_method = PayPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method="",
            operation_id=new_uuid())
        no_reference = PayPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
            payment_method="BANK_TRANSFER", operation_id=new_uuid())
        assert not no_method.success and not no_reference.success
        paid = PayPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method="CASH",
            operation_id=new_uuid())
        assert paid.success
        assert hr_conn.execute(
            "SELECT COUNT(*) FROM payroll_payment_allocations").fetchone()[0] == 1


# ── HR-13 … HR-17 / HR-22 — tiempo ──────────────────────────────────────────
class TestTimeRules:
    def test_night_shift_is_one_workday(self, hr_conn):
        emp = _employee(hr_conn)
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 22))
        _punch(hr_conn, emp, PunchType.EXIT, _local(date(2026, 7, 2), 6))
        workday = _workday(hr_conn, emp, JULY_1)
        assert workday.status is WorkdayStatus.COMPLETE and workday.worked_minutes == 480
        assert _workday(hr_conn, emp, date(2026, 7, 2)) is None

    def test_split_segments_sum_and_extra_exit_is_an_incident(self, hr_conn):
        emp = _employee(hr_conn)
        for kind, hour in ((PunchType.ENTRY, 9), (PunchType.EXIT, 12),
                           (PunchType.ENTRY, 14), (PunchType.EXIT, 17)):
            _punch(hr_conn, emp, kind, _local(JULY_1, hour))
        assert _workday(hr_conn, emp, JULY_1).worked_minutes == 360
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 18))
        workday = _workday(hr_conn, emp, JULY_1)
        assert workday.worked_minutes == 360
        assert workday.incident_type is AttendanceIncidentType.OUT_OF_SEQUENCE

    def _shift(self, conn, emp, *, break_minutes=0):
        shift = CreateShiftUseCase().execute(
            conn, actor_user_id=new_uuid(), name=f"T{break_minutes}", start_time=time(9),
            end_time=time(17), break_minutes=break_minutes)
        AssignShiftUseCase().execute(conn, actor_user_id=new_uuid(), employee_id=emp,
                                     work_shift_id=shift.entity_id,
                                     effective_from=date(2026, 6, 1),
                                     weekdays=(0, 1, 2, 3, 4, 5, 6))
        return shift.entity_id

    def test_unpaid_break_is_deducted_from_worked_time(self, hr_conn):
        emp = _employee(hr_conn)
        self._shift(hr_conn, emp, break_minutes=60)
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 9))
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 17))
        workday = _workday(hr_conn, emp, JULY_1)
        assert (workday.worked_minutes, workday.overtime_minutes) == (420, 0)

    def test_resolved_shift_is_kept_and_recalculation_is_stable(self, hr_conn):
        emp = _employee(hr_conn)
        shift_id = self._shift(hr_conn, emp)
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 9))
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 18))
        workday = _workday(hr_conn, emp, JULY_1)
        assert workday.scheduled_shift_id == shift_id and workday.overtime_minutes == 60
        RecalculateWorkdayUseCase().execute(hr_conn, workday_id=workday.id)
        assert _workday(hr_conn, emp, JULY_1).overtime_minutes == 60

    def test_approved_adjustment_recalculates_and_survives_rebuild(self, hr_conn):
        emp = _employee(hr_conn)
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 9))
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 17))
        workday = _workday(hr_conn, emp, JULY_1)
        request = RequestAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), workday_id=workday.id,
            field_name="last_exit_at", requested_value=datetime(2026, 7, 1, 19, 0),
            reason="inventario", operation_id=new_uuid())
        assert request.success, request.message
        ApproveAttendanceAdjustmentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), adjustment_id=request.entity_id,
            operation_id=new_uuid())
        assert _workday(hr_conn, emp, JULY_1).worked_minutes == 600
        RecalculateWorkdayUseCase().execute(hr_conn, workday_id=workday.id)
        rebuilt = _workday(hr_conn, emp, JULY_1)
        assert rebuilt.worked_minutes == 600 and rebuilt.status is WorkdayStatus.ADJUSTED
        assert AttendanceCalculator().summarize([rebuilt]).present_days == 1

    def test_adjustment_rejects_arbitrary_fields_and_incoherent_times(self, hr_conn):
        emp = _employee(hr_conn)
        _punch(hr_conn, emp, PunchType.ENTRY, _local(JULY_1, 9))
        _punch(hr_conn, emp, PunchType.EXIT, _local(JULY_1, 17))
        workday = _workday(hr_conn, emp, JULY_1)
        for field, value in (("worked_minutes", "9999"),
                             ("last_exit_at", datetime(2026, 7, 1, 8, 0))):
            result = RequestAttendanceAdjustmentUseCase().execute(
                hr_conn, actor_user_id=new_uuid(), workday_id=workday.id, field_name=field,
                requested_value=value, reason="x", operation_id=new_uuid())
            assert not result.success

    def test_manual_local_time_is_stored_as_its_utc_instant(self, hr_conn):
        emp = _employee(hr_conn)
        RegisterManualAttendanceUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH_A,
            punch_type="ENTRY", occurred_at=datetime(2026, 7, 1, 9, 0), reason="sin caja",
            operation_id=new_uuid())
        stored = hr_conn.execute("SELECT occurred_at FROM attendance_punches").fetchone()[0]
        assert stored == "2026-07-01T15:00:00+00:00"

    def test_work_date_uses_branch_timezone(self, hr_conn):
        emp = _employee(hr_conn)
        _punch(hr_conn, emp, PunchType.ENTRY, datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc))
        assert _workday(hr_conn, emp, JULY_1) is not None
        assert _workday(hr_conn, emp, date(2026, 7, 2)) is None


# ── HR-18 / HR-19 — ausencias ───────────────────────────────────────────────
class TestLeave:
    def test_previous_cycle_consumption_does_not_cancel_new_entitlement(self, hr_conn):
        emp = _employee(hr_conn, hire=date(2024, 3, 1))
        first = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH_A,
            leave_type="VACATION", start_date=date(2025, 4, 1), end_date=date(2025, 4, 14),
            reason="ciclo 2", operation_id=new_uuid())
        assert first.success, first.message       # 2.º año: 14 días
        ApproveLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                      leave_id=first.entity_id, operation_id=new_uuid())
        later = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH_A,
            leave_type="VACATION", start_date=date(2026, 4, 6), end_date=date(2026, 4, 6),
            reason="ciclo 3", operation_id=new_uuid())
        assert later.success, later.message

    def test_self_approval_and_unrelated_cancellation_are_refused(self, hr_conn):
        emp = _employee(hr_conn)
        requester = new_uuid()
        leave = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=requester, employee_id=emp, branch_id=BRANCH_A,
            leave_type="PAID_LEAVE", start_date=date(2026, 8, 3), end_date=date(2026, 8, 3),
            reason="trámite", operation_id=new_uuid())
        session = _Session(requester, BRANCH_A, {HRPermission.VIEW, HRPermission.LEAVE_APPROVE,
                                                 HRPermission.LEAVE_REQUEST})
        policy = AuthorizationPolicy(HRSessionPermissionChecker(session))
        own = ApproveLeaveUseCase(policy).execute(
            hr_conn, actor_user_id=requester, leave_id=leave.entity_id, operation_id=new_uuid())
        assert not own.success and "propia" in own.message
        stranger = new_uuid()
        stranger_policy = AuthorizationPolicy(HRSessionPermissionChecker(
            _Session(stranger, BRANCH_A, {HRPermission.VIEW, HRPermission.LEAVE_REQUEST})))
        cancelled = CancelLeaveUseCase(stranger_policy).execute(
            hr_conn, actor_user_id=stranger, leave_id=leave.entity_id, operation_id=new_uuid())
        assert not cancelled.success and cancelled.error_code == "NOT_OWNER"

    def test_cancelling_an_approved_leave_needs_reason_and_publishes_event(self, hr_conn):
        emp = _employee(hr_conn)
        leave = RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, branch_id=BRANCH_A,
            leave_type="PAID_LEAVE", start_date=date(2026, 8, 3), end_date=date(2026, 8, 3),
            reason="trámite", operation_id=new_uuid())
        ApproveLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                      leave_id=leave.entity_id, operation_id=new_uuid())
        without_reason = CancelLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), leave_id=leave.entity_id,
            operation_id=new_uuid())
        assert not without_reason.success
        done = CancelLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), leave_id=leave.entity_id,
            operation_id=new_uuid(), reason="se reprogramó")
        assert done.success
        assert hr_conn.execute(
            "SELECT COUNT(*) FROM hr_outbox WHERE event_name='LEAVE_CANCELLED'").fetchone()[0] == 1


# ── HR-23 / HR-24 / HR-25 / HR-26 / HR-28 ───────────────────────────────────
class TestDataIntegrity:
    def test_update_enforces_creation_invariants_and_records_history(self, hr_conn):
        emp = _employee(hr_conn)
        for fields in ({"first_name": ""}, {"daily_salary": "-100"}):
            result = UpdateEmployeeUseCase().execute(
                hr_conn, actor_user_id=new_uuid(), employee_id=emp, operation_id=new_uuid(),
                **fields)
            assert not result.success
        assert UpdateEmployeeUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp, operation_id=new_uuid(),
            daily_salary="350.00", salary_effective_from=date(2026, 8, 1)).success
        history = EmployeeQueryService(hr_conn).salary_history(emp)
        assert [h["daily_salary"] for h in history] == ["350.00", "300.00"]

    def test_dashboard_open_entry_is_on_shift_and_scope_is_uniform(self, hr_conn):
        emp_a = _employee(hr_conn)
        emp_b = _employee(hr_conn, branch=BRANCH_B)
        today = date(2026, 7, 6)
        _punch(hr_conn, emp_a, PunchType.ENTRY, _local(today, 9))
        _punch(hr_conn, emp_b, PunchType.ENTRY, _local(today, 9), branch=BRANCH_B)
        _punch(hr_conn, emp_b, PunchType.EXIT, _local(today, 19), branch=BRANCH_B)
        RequestLeaveUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=emp_b, branch_id=BRANCH_B,
            leave_type="PAID_LEAVE", start_date=date(2026, 8, 3), end_date=date(2026, 8, 3),
            reason="b", operation_id=new_uuid())
        kpis = HRDashboardQueryService(hr_conn).overview(work_date=today.isoformat(),
                                                         branch_id=BRANCH_A)
        assert kpis["on_shift_now"] == 1 and kpis["absences_today"] == 0
        assert kpis["pending_requests"] == 0 and kpis["overtime_minutes"] == 0

    def test_payroll_totals_are_exact_decimals(self, hr_conn):
        emp = _employee(hr_conn)
        run = PayrollRun.create(JULY_1, JULY_7, new_uuid(), branch_id=BRANCH_A)
        run.add_line(PayrollLine.create(run.id, emp, PayrollConcept.BASE_SALARY,
                                        Money.from_string("0.30"), is_deduction=False))
        run.add_line(PayrollLine.create(run.id, emp, PayrollConcept.LATE_DEDUCTION,
                                        Money.from_string("0.10"), is_deduction=True))
        with HRUnitOfWork(hr_conn) as uow:
            uow.payroll.save(run)
        assert PayrollQueryService(hr_conn).run_totals(run.id)["net"] == "0.20"

    def test_outer_rollback_undoes_nested_use_case(self, hr_conn):
        with pytest.raises(RuntimeError):
            with HRUnitOfWork(hr_conn):
                _employee(hr_conn)
                raise RuntimeError("falla del llamador")
        assert hr_conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0

    def test_employee_101_is_reachable_by_page_and_search(self, hr_conn):
        for index in range(101):
            _employee(hr_conn, code=f"P{index:03d}")
        service = EmployeeQueryService(hr_conn)
        assert service.count_employees(branch_id=BRANCH_A) == 101
        assert len(service.list_employees(branch_id=BRANCH_A, limit=50, offset=100)) == 1
        assert [e["employee_code"] for e in service.list_employees(
            branch_id=BRANCH_A, search="P100")] == ["P100"]


def test_sqlite_coverage_key_is_structural(hr_conn):
    """HR-10: aunque dos procesos lleguen a insertar, la llave lo impide."""
    emp = _employee(hr_conn)
    run_a = PayrollRun.create(JULY_1, JULY_7, new_uuid(), branch_id=BRANCH_A)
    run_b = PayrollRun.create(JULY_1, JULY_7, new_uuid(), branch_id=BRANCH_A)
    with HRUnitOfWork(hr_conn) as uow:
        for run in (run_a, run_b):
            run.add_line(PayrollLine.create(run.id, emp, PayrollConcept.BASE_SALARY,
                                            Money.from_string("1"), is_deduction=False))
            uow.payroll.save(run)
        uow.payroll.claim_coverage(run_a.id, emp, [JULY_1])
        with pytest.raises(sqlite3.IntegrityError):
            uow.payroll.claim_coverage(run_b.id, emp, [JULY_1])
