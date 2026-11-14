"""SDLC-HR-001 — cuentas del asiento de nómina.

Las faltas y los retardos son sueldo NO devengado: bajan el gasto y no son una
retención por enterar. Antes el asiento cuadraba, pero acreditaba 2125 por dinero
que nadie va a enterar y sobrestimaba el gasto de sueldos.

La cuota patronal la calcula el sistema: el pago toma el importe de un proveedor
y Finanzas la provisiona (Dr 6105 / Cr 2125). Sin tablas oficiales configuradas el
proveedor por omisión no inventa una tasa.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.application.event_handlers.finance.payroll_paid_handler import PayrollPaidHandler
from backend.application.use_cases.hr.employee_use_cases import CreateEmployeeUseCase
from backend.application.use_cases.hr.finance_wiring import dispatch_hr_outbox, wire_hr_finance
from backend.application.use_cases.hr.payroll_use_cases import PayPayrollRunUseCase
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.hr.entities import PayrollLine, PayrollRun
from backend.domain.hr.enums import PayrollConcept
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.domain.hr.services.employer_contribution import NoEmployerContributionProvider
from backend.domain.hr.value_objects import Money
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events.application_bus import get_bus, reset_bus
from backend.shared.ids import new_uuid


class _AllowAll:
    def has_permission(self, user_id, code):
        return True


class _TwentyPercent:
    """Motor de prueba: el 20 % de lo devengado. La tasa real no está decidida."""

    def employer_contribution(self, run):
        earned = run.gross_amount().subtract(run.unearned_deductions())
        return earned.multiply("0.20")


@pytest.fixture(autouse=True)
def _isolated_bus():
    reset_bus()
    yield
    reset_bus()


def _balance(conn, code):
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id=jl.journal_entry_id"
        " JOIN accounts a ON a.id=jl.account_id WHERE a.code=?"
        " AND je.status IN ('POSTED','REVERSED')", (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _employee(conn, branch):
    return CreateEmployeeUseCase(AuthorizationPolicy(_AllowAll())).execute(
        conn, actor_user_id=new_uuid(), employee_code="N-1", first_name="Ana",
        last_name="Pérez", branch_id=branch, contract_type="PERMANENT",
        payment_frequency="WEEKLY", base_salary="0.00", daily_salary="300.00",
        hire_date=date(2025, 1, 1), operation_id=new_uuid()).entity_id


def _paid_run(conn, lines, *, provider=None):
    """Corrida real por los casos de uso de pago, con las líneas del escenario."""
    create_hr_schema(conn)
    branch = new_uuid()
    employee = _employee(conn, branch)
    run = PayrollRun.create(date(2026, 7, 1), date(2026, 7, 7), new_uuid(), branch_id=branch,
                            generated_by_user_id=new_uuid())
    for concept, amount, deduction in lines:
        run.add_line(PayrollLine.create(run.id, employee, concept, Money.from_string(amount),
                                        is_deduction=deduction))
    run.mark_calculated()
    run.authorize(new_uuid())
    with HRUnitOfWork(conn) as uow:
        uow.payroll.save(run)
    use_case = PayPayrollRunUseCase(AuthorizationPolicy(_AllowAll()),
                                    **({"employer_contribution": provider} if provider else {}))
    paid = use_case.execute(conn, actor_user_id=new_uuid(), payroll_run_id=run.id,
                            payment_method="BANK_TRANSFER", payment_reference="SPEI-1",
                            operation_id=new_uuid(),
                            paid_at=datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc))
    assert paid.success, paid.message
    return run.id


def _post(conn):
    bus = get_bus()
    wire_hr_finance(bus, conn)
    result = dispatch_hr_outbox(conn, bus)
    assert result["failed"] == 0, result


def _payload(conn):
    return json.loads(conn.execute("SELECT payload_json FROM hr_outbox WHERE"
                                   " event_name='PAYROLL_PAID'").fetchone()[0])


BASE = (PayrollConcept.BASE_SALARY, "2100.00", False)
OVERTIME = (PayrollConcept.OVERTIME, "100.00", False)
ABSENCE = (PayrollConcept.ABSENCE_DEDUCTION, "300.00", True)
LATE = (PayrollConcept.LATE_DEDUCTION, "50.00", True)
LOAN = (PayrollConcept.LOAN_DEDUCTION, "150.00", True)
ISR = (PayrollConcept.TAX_WITHHOLDING, "80.00", True)
IMSS_OBRERO = (PayrollConcept.SOCIAL_SECURITY, "20.00", True)


class TestFaltasYRetardos:
    def test_they_reduce_the_expense_and_create_no_liability(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn, [BASE, OVERTIME, ABSENCE, LATE])
        _post(bootstrapped_conn)
        assert _balance(bootstrapped_conn, "6101") == Decimal("1850.00")
        assert _balance(bootstrapped_conn, "2125") == Decimal("0")
        assert _balance(bootstrapped_conn, "1110") == Decimal("-1850.00")

    def test_payload_separates_them_from_the_withholdings(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn, [BASE, ABSENCE, LATE, ISR])
        payload = _payload(bootstrapped_conn)
        assert payload["unearned_deductions"] == "350.00"
        assert payload["gross_salaries"] == "2100.00"
        assert payload["net_paid"] == "1670.00"

    def test_real_withholdings_still_go_to_the_liability(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn, [BASE, OVERTIME, ABSENCE, LATE, LOAN, ISR, IMSS_OBRERO])
        _post(bootstrapped_conn)
        assert _balance(bootstrapped_conn, "6101") == Decimal("1850.00")
        assert _balance(bootstrapped_conn, "2125") == Decimal("-100.00")   # ISR + obrera
        assert _balance(bootstrapped_conn, "1145") == Decimal("-150.00")   # préstamo
        assert _balance(bootstrapped_conn, "1110") == Decimal("-1600.00")

    def test_event_paid_before_this_change_still_posts(self, bootstrapped_conn):
        PayrollPaidHandler(bootstrapped_conn).handle({
            "event_id": new_uuid(), "operation_id": new_uuid(), "payroll_run_id": new_uuid(),
            "occurred_at": "2026-07-16T12:00:00", "gross_salaries": "1000.00",
            "net_paid": "900.00", "payment_method": "BANK_TRANSFER"})
        assert _balance(bootstrapped_conn, "2125") == Decimal("-100.00")

    def test_unearned_above_the_gross_is_rejected(self, bootstrapped_conn):
        with pytest.raises(FinanceDomainError):
            PayrollPaidHandler(bootstrapped_conn).handle({
                "event_id": new_uuid(), "operation_id": new_uuid(),
                "payroll_run_id": new_uuid(), "occurred_at": "2026-07-16T12:00:00",
                "gross_salaries": "100.00", "unearned_deductions": "200.00",
                "net_paid": "10.00", "payment_method": "BANK_TRANSFER"})


class TestCuotaPatronal:
    def test_is_provisioned_against_its_liability(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn, [BASE, OVERTIME, ABSENCE, LATE, LOAN, ISR, IMSS_OBRERO],
                  provider=_TwentyPercent())
        assert _payload(bootstrapped_conn)["social_security"] == "370.00"
        _post(bootstrapped_conn)
        assert _balance(bootstrapped_conn, "6105") == Decimal("370.00")
        assert _balance(bootstrapped_conn, "2125") == Decimal("-470.00")   # 370 + 100
        assert _balance(bootstrapped_conn, "6101") == Decimal("1850.00")
        rows = bootstrapped_conn.execute(
            "SELECT debit_amount, credit_amount FROM journal_lines").fetchall()
        assert sum(Decimal(d) for d, _ in rows) == sum(Decimal(c) for _, c in rows)

    def test_without_official_tables_no_rate_is_invented(self, bootstrapped_conn):
        _paid_run(bootstrapped_conn, [BASE])
        assert _payload(bootstrapped_conn)["social_security"] == "0.00"
        assert "no configuradas" in NoEmployerContributionProvider.name
