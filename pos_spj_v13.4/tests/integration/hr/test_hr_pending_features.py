"""Pendientes de RR. HH. (2026-10-14): recibo de nómina, checador, conceptos,
préstamos, corrida complementaria, reverso de pago, libro de vacaciones y el
puerto de retenciones. Clases reales sobre SQLite con ``foreign_keys``."""

from __future__ import annotations

import sys
import types
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.hr.payroll_receipts import (
    ExportPayrollReceiptsPdfUseCase,
    PayrollReceiptService,
    PrintPayrollReceiptTicketUseCase,
)
from backend.application.use_cases.hr.attendance_use_cases import RegisterAttendancePunchUseCase
from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.application.use_cases.hr.leave_use_cases import (
    AdjustLeaveBalanceUseCase,
    ApproveLeaveUseCase,
    CancelLeaveUseCase,
    RequestLeaveUseCase,
    VacationBalanceQuery,
)
from backend.application.use_cases.hr.payroll_adjustment_use_cases import (
    GenerateComplementaryPayrollRunUseCase,
    ReversePayrollPaymentUseCase,
)
from backend.application.use_cases.hr.payroll_inputs_use_cases import (
    CapturePayrollInputUseCase,
    GrantEmployeeLoanUseCase,
    ResolvePayrollInputUseCase,
)
from backend.application.use_cases.hr.payroll_use_cases import (
    AuthorizePayrollRunUseCase,
    CancelPayrollRunUseCase,
    GeneratePayrollRunUseCase,
    PayPayrollRunUseCase,
)
from backend.application.use_cases.hr.time_clock_use_cases import (
    EnrollCredentialUseCase,
    ImportTimeClockFileUseCase,
    KioskPunchUseCase,
    RegisterTimeClockDeviceUseCase,
    SyncTimeClockDeviceUseCase,
)
from backend.domain.hr.enums import PayrollConcept, PayrollRunStatus, PunchType
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.infrastructure.hr.payroll_receipt_renderers import (
    PayrollReceiptEscPosRenderer,
    render_payroll_receipts_pdf,
)
from backend.infrastructure.hr.time_clock_drivers import (
    TIME_CLOCK_DRIVERS,
    parse_attendance_file,
)
from backend.shared.ids import new_uuid

BRANCH = new_uuid()
CDMX = timezone(timedelta(hours=-6))
JULY_1, JULY_7, AFTER = date(2026, 7, 1), date(2026, 7, 7), date(2026, 7, 31)


def _employee(conn, *, code=None, hire=date(2025, 1, 1)) -> str:
    return CreateEmployeeUseCase().execute(
        conn, actor_user_id=new_uuid(), employee_code=code or f"E-{new_uuid()[-6:]}",
        first_name="Ana", last_name="Pérez", branch_id=BRANCH, contract_type="PERMANENT",
        payment_frequency="WEEKLY", base_salary="0", daily_salary="300.00", hire_date=hire,
        operation_id=new_uuid()).entity_id


def _generate(conn, *, start=JULY_1, end=JULY_7):
    return GeneratePayrollRunUseCase().execute(
        conn, actor_user_id=new_uuid(), period_start=start, period_end=end,
        operation_id=new_uuid(), branch_id=BRANCH, today=AFTER)


def _paid(conn, run_id, method="CASH"):
    AuthorizePayrollRunUseCase().execute(conn, actor_user_id=new_uuid(),
                                         payroll_run_id=run_id, operation_id=new_uuid())
    result = PayPayrollRunUseCase().execute(
        conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method=method,
        operation_id=new_uuid(), paid_at=datetime(2026, 7, 8, 18, tzinfo=timezone.utc))
    assert result.success, result.message
    return result


def _run(conn, run_id):
    with HRUnitOfWork(conn) as uow:
        return uow.payroll.get(run_id)


# ── recibo de nómina ────────────────────────────────────────────────────────
class TestPayrollReceipt:
    def test_receipt_reflects_the_paid_run(self, hr_conn):
        _employee(hr_conn, code="R-1")
        run_id = _generate(hr_conn).entity_id
        preliminary = PayrollReceiptService(hr_conn).receipts_for_run(run_id)[0]
        assert preliminary.preliminary
        _paid(hr_conn, run_id)
        receipt = PayrollReceiptService(hr_conn).receipts_for_run(run_id)[0]
        assert not receipt.preliminary and receipt.net == "2,100.00"
        assert receipt.payment_method == "Efectivo" and receipt.folio.endswith("R-1")
        assert [line.concept for line in receipt.perceptions] == ["Sueldo"]

    def test_pdf_and_reprint_marker(self, hr_conn, tmp_path):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _paid(hr_conn, run_id)
        use_case = ExportPayrollReceiptsPdfUseCase(renderer=render_payroll_receipts_pdf)
        path = str(tmp_path / "recibos.pdf")
        assert use_case.execute(hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
                                path=path).success
        assert open(path, "rb").read(4) == b"%PDF"
        assert PayrollReceiptService(hr_conn).receipts_for_run(run_id)[0].reprint

    def test_ticket_is_escpos_at_paper_width(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        receipt = PayrollReceiptService(hr_conn).receipts_for_run(run_id)[0]
        narrow = PayrollReceiptEscPosRenderer(paper_width_mm=58)
        assert max(len(line) for line in narrow.text(receipt).splitlines()) <= 32
        data = narrow.render([receipt])
        assert data.startswith(b"\x1b@") and b"RECIBO DE NOMINA" in data
        assert data.endswith(b"\x1dVA\x00") and b"2,100.00" in data

    def test_ticket_uses_the_routed_printer_and_reports_missing_route(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        sent = []
        printed = PrintPayrollReceiptTicketUseCase(
            printer=lambda receipts, **kw: sent.append(receipts) or "TERMICA-1").execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id, branch_id=BRANCH)
        assert printed.success and len(sent[0]) == 1
        from backend.infrastructure.hardware.payroll_receipt_printer import PayrollReceiptPrinter
        missing = PrintPayrollReceiptTicketUseCase(printer=PayrollReceiptPrinter(hr_conn)).execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id, branch_id=BRANCH)
        assert not missing.success and "Recibo de nómina" in missing.message


# ── checador ────────────────────────────────────────────────────────────────
def _device(conn, *, driver="keyboard", kind="KEYBOARD_READER", settings=None) -> str:
    result = RegisterTimeClockDeviceUseCase().execute(
        conn, actor_user_id=new_uuid(), branch_id=BRANCH, code=f"CH-{new_uuid()[-4:]}",
        name="Entrada", kind=kind, driver=driver, connection_settings=settings)
    assert result.success, result.message
    return result.entity_id


class TestTimeClock:
    def test_kiosk_card_scan_toggles_entry_and_exit_and_ignores_double_scan(self, hr_conn):
        employee = _employee(hr_conn)
        device = _device(hr_conn)
        assert EnrollCredentialUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=employee, credential_type="CARD",
            raw_value="00A1B2").success
        start = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
        kiosk = KioskPunchUseCase()
        first = kiosk.execute(hr_conn, actor_user_id=new_uuid(), device_id=device,
                              credential_type="CARD", raw_value="00a1b2", now=start)
        double = kiosk.execute(hr_conn, actor_user_id=new_uuid(), device_id=device,
                               credential_type="CARD", raw_value="00A1B2",
                               now=start + timedelta(seconds=10))
        later = kiosk.execute(hr_conn, actor_user_id=new_uuid(), device_id=device,
                              credential_type="CARD", raw_value="00A1B2",
                              now=start + timedelta(hours=8))
        assert first.success and double.data.get("duplicated") and later.success
        punches = hr_conn.execute("SELECT punch_type, source, device_id FROM attendance_punches"
                                  " ORDER BY occurred_at").fetchall()
        assert [p[0] for p in punches] == ["ENTRY", "EXIT"]
        assert {p[1] for p in punches} == {"TIME_CLOCK"} and {p[2] for p in punches} == {device}

    def test_unknown_card_is_kept_and_applied_when_enrolled(self, hr_conn):
        employee = _employee(hr_conn)
        device = _device(hr_conn)
        unknown = KioskPunchUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), device_id=device, credential_type="CARD",
            raw_value="FFEE01", now=datetime(2026, 7, 1, 15, tzinfo=timezone.utc))
        assert not unknown.success and unknown.error_code == "UNMATCHED"
        enrolled = EnrollCredentialUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=employee, credential_type="CARD",
            raw_value="FFEE01")
        assert enrolled.data["reprocessed"] == 1
        assert hr_conn.execute("SELECT COUNT(*) FROM attendance_punches").fetchone()[0] == 1

    def test_pin_is_stored_hashed_and_duplicates_are_refused(self, hr_conn):
        first, second = _employee(hr_conn), _employee(hr_conn)
        enroll = EnrollCredentialUseCase()
        assert enroll.execute(hr_conn, actor_user_id=new_uuid(), employee_id=first,
                              credential_type="PIN", raw_value="4821").success
        stored = hr_conn.execute("SELECT lookup_key, label FROM hr_employee_credentials").fetchone()
        assert "4821" not in stored[0] and stored[1] == "PIN"
        dup = enroll.execute(hr_conn, actor_user_id=new_uuid(), employee_id=second,
                             credential_type="PIN", raw_value="4821")
        assert not dup.success and dup.error_code == "DUPLICATE_CREDENTIAL"

    def test_exported_attlog_file_imports_once_in_branch_time(self, hr_conn, tmp_path):
        employee = _employee(hr_conn)
        device = _device(hr_conn, driver="attlog_file", kind="FINGERPRINT")
        EnrollCredentialUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                          employee_id=employee, credential_type="DEVICE_USER",
                                          raw_value="7", device_id=device)
        attlog = tmp_path / "attlog.dat"
        attlog.write_text("7\t2026-07-01 09:00:00\t1\t0\n7\t2026-07-01 17:00:00\t1\t1\n",
                          encoding="utf-8")
        importer = ImportTimeClockFileUseCase(parser=parse_attendance_file)
        first = importer.execute(hr_conn, actor_user_id=new_uuid(), device_id=device,
                                 path=str(attlog))
        again = importer.execute(hr_conn, actor_user_id=new_uuid(), device_id=device,
                                 path=str(attlog))
        assert first.data["applied"] == 2 and again.data["duplicate"] == 2
        row = hr_conn.execute("SELECT occurred_at, source FROM attendance_punches"
                              " ORDER BY occurred_at").fetchone()
        assert row == ("2026-07-01T15:00:00+00:00", "FINGERPRINT")
        with HRUnitOfWork(hr_conn) as uow:
            assert uow.attendance.find_workday(employee, JULY_1).worked_minutes == 480

    def test_network_driver_contract_with_pyzk(self, hr_conn, monkeypatch):
        employee = _employee(hr_conn)
        device = _device(hr_conn, driver="zkteco", kind="FINGERPRINT",
                         settings={"host": "192.168.1.50"})
        EnrollCredentialUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                          employee_id=employee, credential_type="DEVICE_USER",
                                          raw_value="12", device_id=device)
        record = types.SimpleNamespace(user_id="12", timestamp=datetime(2026, 7, 2, 8, 55),
                                       status=1, punch=0)

        class _Conn:
            def get_attendance(self):
                return [record]

            def disconnect(self):
                pass

        class _ZK:
            def __init__(self, *a, **k):
                pass

            def connect(self):
                return _Conn()

        monkeypatch.setitem(sys.modules, "zk", types.SimpleNamespace(ZK=_ZK))
        sync = SyncTimeClockDeviceUseCase(drivers=TIME_CLOCK_DRIVERS)
        first = sync.execute(hr_conn, actor_user_id=new_uuid(), device_id=device)
        second = sync.execute(hr_conn, actor_user_id=new_uuid(), device_id=device)
        assert first.data["applied"] == 1 and second.data["applied"] == 0
        assert hr_conn.execute("SELECT punch_type FROM attendance_punches").fetchone()[0] == "ENTRY"


# ── conceptos, préstamos, retenciones ───────────────────────────────────────
class TestPayrollInputsAndLoans:
    def test_captured_bonus_needs_another_approver_and_enters_the_run(self, hr_conn):
        employee = _employee(hr_conn)
        capturer = new_uuid()
        captured = CapturePayrollInputUseCase().execute(
            hr_conn, actor_user_id=capturer, employee_id=employee, concept="BONUS",
            amount="500", applies_on=date(2026, 7, 3), reason="Meta de ventas",
            operation_id=new_uuid())
        resolver = ResolvePayrollInputUseCase()
        own = resolver.execute(hr_conn, actor_user_id=capturer, input_id=captured.entity_id,
                               approve=True)
        assert not own.success and own.error_code == "SEGREGATION"
        assert resolver.execute(hr_conn, actor_user_id=new_uuid(), input_id=captured.entity_id,
                                approve=True).success
        generated = _generate(hr_conn)
        assert generated.data["net"] == "2600.00"
        CancelPayrollRunUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                          payroll_run_id=generated.entity_id,
                                          operation_id=new_uuid())
        assert hr_conn.execute("SELECT status FROM payroll_inputs").fetchone()[0] == "APPROVED"

    def test_loan_installment_is_deducted_until_paid_without_negative_net(self, hr_conn):
        employee = _employee(hr_conn)
        granted = GrantEmployeeLoanUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), employee_id=employee, kind="LOAN",
            principal="3000", installment="2000", payment_method="CASH",
            reason="Emergencia", operation_id=new_uuid(), granted_on=date(2026, 6, 20))
        assert granted.success
        assert hr_conn.execute("SELECT COUNT(*) FROM hr_outbox WHERE event_name="
                               "'EMPLOYEE_LOAN_GRANTED'").fetchone()[0] == 1
        first = _generate(hr_conn)
        assert first.data["net"] == "100.00"                   # 2100 − 2000
        _paid(hr_conn, first.entity_id)
        second = _generate(hr_conn, start=date(2026, 7, 8), end=date(2026, 7, 14))
        assert second.data["net"] == "1100.00"                 # 2100 − 1000 (saldo)
        _paid(hr_conn, second.entity_id)
        assert hr_conn.execute("SELECT status FROM employee_loans").fetchone()[0] == "PAID"

    def test_withholding_provider_port(self, hr_conn):
        _employee(hr_conn)

        class _Provider:
            def withholdings(self, employee, lines, *, period_start, period_end):
                return [(PayrollConcept.TAX_WITHHOLDING, Money.from_string("120.00"),
                         "ISR de prueba")]

        result = GeneratePayrollRunUseCase(withholding_provider=_Provider()).execute(
            hr_conn, actor_user_id=new_uuid(), period_start=JULY_1, period_end=JULY_7,
            operation_id=new_uuid(), branch_id=BRANCH, today=AFTER)
        assert result.data["net"] == "1980.00"


# ── complementaria y reverso ────────────────────────────────────────────────
class TestPaidRunCorrections:
    def _unpaid_leave(self, conn, employee):
        leave = RequestLeaveUseCase().execute(
            conn, actor_user_id=new_uuid(), employee_id=employee, branch_id=BRANCH,
            leave_type="UNPAID_LEAVE", start_date=date(2026, 7, 2), end_date=date(2026, 7, 3),
            reason="personal", operation_id=new_uuid())
        ApproveLeaveUseCase().execute(conn, actor_user_id=new_uuid(), leave_id=leave.entity_id,
                                      operation_id=new_uuid())
        return leave.entity_id

    def test_complementary_pays_only_the_difference(self, hr_conn):
        employee = _employee(hr_conn)
        leave_id = self._unpaid_leave(hr_conn, employee)
        original = _generate(hr_conn)
        assert original.data["net"] == "1500.00"
        _paid(hr_conn, original.entity_id)
        CancelLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(), leave_id=leave_id,
                                     operation_id=new_uuid(), reason="Sí trabajó")
        complementary = GenerateComplementaryPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), original_run_id=original.entity_id,
            reason="Permiso cancelado", operation_id=new_uuid(), today=AFTER)
        assert complementary.success and complementary.data["net"] == "600.00"
        again = GenerateComplementaryPayrollRunUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), original_run_id=original.entity_id,
            reason="otra vez", operation_id=new_uuid(), today=AFTER)
        assert not again.success and again.error_code == "NO_DIFFERENCE"

    def test_reversing_an_unposted_payment_voids_it_and_frees_the_period(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _paid(hr_conn, run_id)
        reversed_ = ReversePayrollPaymentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id,
            reason="Se pagó la sucursal equivocada", operation_id=new_uuid())
        assert reversed_.success
        assert _run(hr_conn, run_id).status is PayrollRunStatus.CANCELLED
        status, error = hr_conn.execute(
            "SELECT status, last_error FROM hr_outbox WHERE event_name='PAYROLL_PAID'").fetchone()
        assert status == "DISPATCHED" and error.startswith("anulado")
        assert hr_conn.execute("SELECT COUNT(*) FROM hr_outbox WHERE event_name="
                               "'PAYROLL_PAYMENT_REVERSED'").fetchone()[0] == 0
        assert _generate(hr_conn).success

    def test_reversing_a_posted_payment_publishes_the_reversal(self, hr_conn):
        _employee(hr_conn)
        run_id = _generate(hr_conn).entity_id
        _paid(hr_conn, run_id)
        hr_conn.execute("UPDATE hr_outbox SET status='DISPATCHED'")
        ReversePayrollPaymentUseCase().execute(
            hr_conn, actor_user_id=new_uuid(), payroll_run_id=run_id, reason="Error",
            operation_id=new_uuid())
        assert hr_conn.execute("SELECT COUNT(*) FROM hr_outbox WHERE event_name="
                               "'PAYROLL_PAYMENT_REVERSED' AND status='PENDING'").fetchone()[0] == 1


# ── libro de vacaciones ─────────────────────────────────────────────────────
class TestVacationLedger:
    def _request(self, conn, employee, start, end):
        return RequestLeaveUseCase().execute(
            conn, actor_user_id=new_uuid(), employee_id=employee, branch_id=BRANCH,
            leave_type="VACATION", start_date=start, end_date=end, reason="descanso",
            operation_id=new_uuid())

    def test_movements_explain_the_balance(self, hr_conn):
        employee = _employee(hr_conn, hire=date(2025, 3, 1))     # ciclo 2026-03-01: 14 días
        approved = self._request(hr_conn, employee, date(2026, 4, 6), date(2026, 4, 10))
        ApproveLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                      leave_id=approved.entity_id, operation_id=new_uuid())
        pending = self._request(hr_conn, employee, date(2026, 5, 4), date(2026, 5, 5))
        balance = VacationBalanceQuery().execute(hr_conn, employee_id=employee,
                                                 on_date=date(2026, 5, 1))
        assert balance["reserved"] == 2
        kinds = [m["kind"] for m in balance["movements"]]
        assert "CONSUMPTION" in kinds and "RESERVATION" in kinds
        CancelLeaveUseCase().execute(hr_conn, actor_user_id=new_uuid(),
                                     leave_id=pending.entity_id, operation_id=new_uuid())
        after = VacationBalanceQuery().execute(hr_conn, employee_id=employee,
                                               on_date=date(2026, 5, 1))
        assert after["reserved"] == 0
        # FIFO: se consumió del ciclo VIGENTE más antiguo (2025, vence 2026-08-28).
        remaining = {c["cycle_start"]: c["remaining"] for c in after["cycles"]}
        assert remaining == {"2025-03-01": 12 - 5, "2026-03-01": 14}
        assert after["available"] == 7 + 14

    def test_unused_days_expire_after_the_carry_over_window(self, hr_conn):
        employee = _employee(hr_conn, hire=date(2024, 1, 1))
        # ciclo 2024 (12 días) vence 6 meses después de terminar: 2025-06-30
        balance = VacationBalanceQuery().execute(hr_conn, employee_id=employee,
                                                 on_date=date(2025, 8, 1))
        starts = [c["cycle_start"] for c in balance["cycles"]]
        assert "2024-01-01" not in starts and balance["available"] == 14
        expired = [m for m in balance["movements"] if m["kind"] == "EXPIRATION"]
        assert expired and expired[0]["days"] == -12

    def test_manual_adjustment_needs_reason(self, hr_conn):
        employee = _employee(hr_conn)
        adjust = AdjustLeaveBalanceUseCase()
        assert not adjust.execute(hr_conn, actor_user_id=new_uuid(), employee_id=employee,
                                  days=2, reason="", on_date=date(2026, 7, 1)).success
        assert adjust.execute(hr_conn, actor_user_id=new_uuid(), employee_id=employee, days=2,
                              reason="Días por convenio", on_date=date(2026, 7, 1)).success
        balance = VacationBalanceQuery().execute(hr_conn, employee_id=employee,
                                                 on_date=date(2026, 7, 1))
        assert balance["available"] == 14 + 2
