"""FASE 5 — Caja↔Asistencia: apertura/cierre → entrada/salida por eventos."""

from datetime import date, datetime, timezone

import pytest

from backend.application.event_handlers.hr.cash_attendance_handlers import (
    CashShiftClosedAttendanceHandler,
    CashShiftOpenedAttendanceHandler,
)
from backend.application.use_cases.hr.cash_shift_use_cases import (
    CloseCashShiftUseCase,
    ValidateCashOpenerUseCase,
)
from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.domain.hr.enums import WorkdayStatus
from backend.domain.hr.exceptions import UserEmployeeLinkRequiredError
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import new_uuid

BRANCH = new_uuid()


def _linked_employee(conn):
    """Create an employee and a user linked to it; return (user_id, employee_id)."""
    user_id = new_uuid()
    conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'cajero')", (user_id,))
    result = CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=f"E{user_id[:6]}",
        first_name="Ana", last_name="García", branch_id=BRANCH,
        contract_type="PERMANENT", payment_frequency="SEMIMONTHLY",
        base_salary="15000.00", daily_salary="500.00", hire_date=date(2025, 1, 1),
        operation_id=new_uuid(), link_user_id=user_id)
    return user_id, result.entity_id


def _open_payload(user_id, employee_id=None, shift_id=None, hour=9):
    return {
        "event_id": new_uuid(), "operation_id": new_uuid(),
        "shift_id": shift_id or new_uuid(), "branch_id": BRANCH,
        "user_id": user_id, "employee_id": employee_id,
        "opened_at": datetime(2026, 7, 16, hour, 0, tzinfo=timezone.utc).isoformat(),
        "opening_amount": "500.00", "source": "POS",
    }


def _close_payload(user_id, employee_id, shift_id, hour=17):
    return {
        "event_id": new_uuid(), "operation_id": new_uuid(),
        "shift_id": shift_id, "branch_id": BRANCH,
        "user_id": user_id, "employee_id": employee_id,
        "closed_at": datetime(2026, 7, 16, hour, 0, tzinfo=timezone.utc).isoformat(),
        "z_cut_id": new_uuid(), "cash_difference": "0.00", "source": "POS",
    }


class TestCashOpensAttendance:
    def test_open_registers_entry(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        CashShiftOpenedAttendanceHandler(hr_conn).handle(_open_payload(user, emp))
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd is not None and wd.first_entry_at is not None

    def test_close_registers_exit(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        shift = new_uuid()
        CashShiftOpenedAttendanceHandler(hr_conn).handle(
            _open_payload(user, emp, shift_id=shift))
        CashShiftClosedAttendanceHandler(hr_conn).handle(
            _close_payload(user, emp, shift))
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd.status is WorkdayStatus.COMPLETE
        assert wd.worked_minutes == 8 * 60

    def test_repeated_open_does_not_duplicate(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        payload = _open_payload(user, emp)
        handler = CashShiftOpenedAttendanceHandler(hr_conn)
        handler.handle(payload)
        handler.handle(payload)  # same event_id
        count = hr_conn.execute(
            "SELECT COUNT(*) FROM attendance_punches WHERE punch_type='ENTRY'").fetchone()[0]
        assert count == 1

    def test_close_without_entry_creates_incident(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        CashShiftClosedAttendanceHandler(hr_conn).handle(
            _close_payload(user, emp, new_uuid()))
        with HRUnitOfWork(hr_conn) as uow:
            wd = uow.attendance.find_workday(emp, date(2026, 7, 16))
        assert wd.status is WorkdayStatus.INCIDENT
        events = hr_conn.execute(
            "SELECT COUNT(*) FROM hr_outbox WHERE event_name='ATTENDANCE_INCIDENT_CREATED'"
        ).fetchone()[0]
        assert events == 1

    def test_manual_entry_then_cash_open_no_duplicate(self, hr_conn):
        """Registro manual previo no se duplica al abrir caja."""
        from backend.application.use_cases.hr.attendance_use_cases import (
            RegisterManualAttendanceUseCase,
        )
        user, emp = _linked_employee(hr_conn)
        RegisterManualAttendanceUseCase().execute(
            hr_conn, actor_user_id=user, employee_id=emp, branch_id=BRANCH,
            punch_type="ENTRY",
            occurred_at=datetime(2026, 7, 16, 8, 55, tzinfo=timezone.utc),
            reason="llegó antes de abrir caja", operation_id=new_uuid())
        CashShiftOpenedAttendanceHandler(hr_conn).handle(_open_payload(user, emp))
        count = hr_conn.execute(
            "SELECT COUNT(*) FROM attendance_punches WHERE punch_type='ENTRY'").fetchone()[0]
        assert count == 1  # cash open did not duplicate the manual entry

    def test_multiple_cash_shifts_one_workday(self, hr_conn):
        """Varias cajas en un día no crean múltiples jornadas."""
        user, emp = _linked_employee(hr_conn)
        opener = CashShiftOpenedAttendanceHandler(hr_conn)
        closer = CashShiftClosedAttendanceHandler(hr_conn)
        shift1, shift2 = new_uuid(), new_uuid()
        opener.handle(_open_payload(user, emp, shift_id=shift1, hour=9))
        closer.handle(_close_payload(user, emp, shift1, hour=13))
        opener.handle(_open_payload(user, emp, shift_id=shift2, hour=14))
        closer.handle(_close_payload(user, emp, shift2, hour=18))
        workdays = hr_conn.execute(
            "SELECT COUNT(*) FROM attendance_workdays WHERE employee_id=?", (emp,)).fetchone()[0]
        assert workdays == 1  # a single workday for the date


class TestCashOpenerValidation:
    def test_unlinked_user_blocked(self, hr_conn):
        user = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'x')", (user,))
        result = ValidateCashOpenerUseCase().execute(hr_conn, user_id=user)
        assert not result.success and result.error_code == "USER_NOT_LINKED"

    def test_handler_raises_for_unlinked_user(self, hr_conn):
        user = new_uuid()
        hr_conn.execute("INSERT INTO usuarios (id, usuario) VALUES (?, 'x')", (user,))
        with pytest.raises(UserEmployeeLinkRequiredError):
            CashShiftOpenedAttendanceHandler(hr_conn).handle(
                _open_payload(user, employee_id=None))

    def test_linked_active_user_ok(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        result = ValidateCashOpenerUseCase().execute(hr_conn, user_id=user)
        assert result.success and result.data["employee_id"] == emp


class TestCloseCashShiftUseCase:
    def test_publishes_canonical_event_with_identity(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        result = CloseCashShiftUseCase().execute(
            hr_conn, shift_id=new_uuid(), branch_id=BRANCH, user_id=user,
            operation_id=new_uuid())
        assert result.success and result.data["employee_id"] == emp
        row = hr_conn.execute(
            "SELECT payload_json FROM hr_outbox WHERE event_name='CASH_SHIFT_CLOSED'"
        ).fetchone()
        import json
        payload = json.loads(row[0])
        assert payload["user_id"] == user and payload["employee_id"] == emp

    def test_config_flag_disables_entry(self, hr_conn):
        user, emp = _linked_employee(hr_conn)
        handler = CashShiftOpenedAttendanceHandler(
            hr_conn, config_getter=lambda k: False)
        handler.handle(_open_payload(user, emp))
        count = hr_conn.execute("SELECT COUNT(*) FROM attendance_punches").fetchone()[0]
        assert count == 0
