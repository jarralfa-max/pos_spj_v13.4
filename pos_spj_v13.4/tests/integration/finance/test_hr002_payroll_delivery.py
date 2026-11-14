"""SDLC-HR-002 — el asiento de nómina se reintenta solo y la pantalla lo dice.

Antes ``hr_outbox`` sólo se entregaba justo después de pagar y al arrancar, y el
presenter ignoraba el resultado: decía «Nómina pagada» aunque Finanzas fallara, y
el asiento esperaba al siguiente reinicio.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.application.use_cases.hr.finance_wiring import dispatch_hr_outbox, wire_hr_finance
from backend.application.use_cases.hr.payroll_use_cases import (
    AuthorizePayrollRunUseCase,
    GeneratePayrollRunUseCase,
    PayPayrollRunUseCase,
)
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events.application_bus import get_bus, reset_bus
from backend.shared.ids import new_uuid
from frontend.desktop.modules.hr.hr_presenter import HRPresenter
from frontend.desktop.shell import desktop_shell_window_composition as shell


class _AllowAll:
    def has_permission(self, user_id, code):
        return True


@pytest.fixture(autouse=True)
def _isolated_bus():
    reset_bus()
    yield
    reset_bus()


def _presenter(dispatcher):
    pay = SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(success=True,
                                                                  message="Nómina pagada"))
    use_cases = {"pay_payroll": pay}
    if dispatcher is not None:
        use_cases["dispatch_outbox"] = dispatcher
    return HRPresenter(connection_provider=lambda: None, query_services={}, use_cases=use_cases,
                       session_context=SimpleNamespace(user_id="u1"))


def _pay(presenter):
    return presenter.pay_payroll("run-1", payment_method="CASH")


class TestAvisoEnPantalla:
    def test_delivered_entry_keeps_the_plain_message(self):
        ok, message = _pay(_presenter(lambda: {"failed": 0, "without_consumer": 0}))
        assert ok and message == "Nómina pagada"

    def test_finance_failure_is_reported(self):
        ok, message = _pay(_presenter(lambda: {"failed": 1, "without_consumer": 0}))
        assert ok and "Nómina pagada" in message and "pendiente" in message

    def test_missing_consumer_is_reported(self):
        ok, message = _pay(_presenter(lambda: {"failed": 0, "without_consumer": 1}))
        assert ok and "pendiente" in message

    def test_dispatcher_crash_is_reported(self):
        def explode():
            raise RuntimeError("base ocupada")
        ok, message = _pay(_presenter(explode))
        assert ok and "pendiente" in message

    def test_rejected_payment_is_not_dressed_up(self):
        presenter = _presenter(lambda: {"failed": 1, "without_consumer": 0})
        presenter._use_cases["pay_payroll"] = SimpleNamespace(
            execute=lambda *a, **k: SimpleNamespace(success=False, message="Sin autorización"))
        assert _pay(presenter) == (False, "Sin autorización")


def _paid_run(conn):
    create_hr_schema(conn)
    auth = AuthorizationPolicy(_AllowAll())
    branch = new_uuid()
    CreateEmployeeUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), employee_code="N-1", first_name="Ana",
        last_name="Pérez", branch_id=branch, contract_type="PERMANENT",
        payment_frequency="WEEKLY", base_salary="0.00", daily_salary="300.00",
        hire_date=date(2025, 1, 1), operation_id=new_uuid())
    run_id = GeneratePayrollRunUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7), operation_id=new_uuid(), branch_id=branch,
        today=date(2026, 7, 16)).entity_id
    AuthorizePayrollRunUseCase(auth).execute(conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
    paid = PayPayrollRunUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method="CASH",
        operation_id=new_uuid(), paid_at=datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc))
    assert paid.success, paid.message


def _entries(conn):
    return conn.execute("SELECT COUNT(*) FROM journal_entries WHERE source_module='hr'"
                        ).fetchone()[0]


class TestCicloPeriodico:
    def test_the_tick_delivers_what_failed_after_paying(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn)
        first = dispatch_hr_outbox(bootstrapped_conn, get_bus())      # Finanzas aún sin escuchar
        assert first["without_consumer"] == 1 and _entries(bootstrapped_conn) == 0
        wire_hr_finance(get_bus(), bootstrapped_conn)
        result = shell._hr_outbox_tick(bootstrapped_conn)()
        assert result["dispatched"] == 1 and _entries(bootstrapped_conn) == 1

    def test_repeating_the_tick_does_not_duplicate_the_entry(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn)
        wire_hr_finance(get_bus(), bootstrapped_conn)
        tick = shell._hr_outbox_tick(bootstrapped_conn)
        tick()
        tick()
        assert _entries(bootstrapped_conn) == 1

    def test_the_shell_schedules_it(self):
        source = inspect.getsource(shell._build_background_services)
        assert '"hr.outbox"' in source and "_hr_outbox_tick(connection)" in source
        assert shell.HR_OUTBOX_INTERVAL_MS <= 5 * 60 * 1000
