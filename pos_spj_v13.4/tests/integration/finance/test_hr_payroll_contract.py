"""Auditoría RRHH cebf67a HR-03/HR-04/HR-29 — nómina pagada → contabilidad.

El sobre lo produce el caso de uso REAL de RR. HH. (sin repararlo a mano), lo
entrega el despachador real del ``hr_outbox`` por el bus y lo consume el
manejador real de Finanzas: un solo asiento, reentregar no duplica, y el método
de pago decide la cuenta (efectivo → caja 1101; transferencia → bancos 1110).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

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


class _AllowAll:
    def has_permission(self, user_id, code):
        return True


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
        " AND je.status IN ('POSTED','REVERSED')",
        (code,)).fetchall()
    return sum((Decimal(d) - Decimal(c) for d, c in rows), Decimal("0"))


def _paid_run(conn, method, reference=None) -> str:
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
        conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method=method,
        payment_reference=reference, operation_id=new_uuid(),
        paid_at=datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc))
    assert paid.success, paid.message
    return run_id


def test_real_payload_reaches_the_ledger_once_and_cash_credits_cash(bootstrapped_conn):
    conn = bootstrapped_conn
    _paid_run(conn, "CASH")
    bus = get_bus()
    wire_hr_finance(bus, conn)
    first = dispatch_hr_outbox(conn, bus)
    assert first["failed"] == 0 and first["without_consumer"] == 0
    conn.execute("UPDATE hr_outbox SET status='PENDING' WHERE event_name='PAYROLL_PAID'")
    conn.commit()
    dispatch_hr_outbox(conn, bus)                      # reentrega: idempotente
    entries = conn.execute(
        "SELECT COUNT(*) FROM journal_entries WHERE source_module='hr'").fetchone()[0]
    assert entries == 1
    assert _balance(conn, "1101") == Decimal("-2100.00")   # Cr Caja
    assert _balance(conn, "1110") == Decimal("0")          # no toca bancos
    assert _balance(conn, "6101") == Decimal("2100.00")


def test_transfer_credits_the_bank(bootstrapped_conn):
    conn = bootstrapped_conn
    _paid_run(conn, "BANK_TRANSFER", reference="SPEI-77")
    bus = get_bus()
    wire_hr_finance(bus, conn)
    dispatch_hr_outbox(conn, bus)
    assert _balance(conn, "1110") == Decimal("-2100.00")
    assert _balance(conn, "1101") == Decimal("0")


def test_without_consumer_the_payment_stays_pending_and_visible(bootstrapped_conn):
    from backend.application.use_cases.hr.finance_wiring import pending_report
    conn = bootstrapped_conn
    _paid_run(conn, "CASH")
    result = dispatch_hr_outbox(conn, get_bus())       # bus sin suscriptores
    assert result["without_consumer"] == 1
    assert [r["event_name"] for r in pending_report(conn)] == ["PAYROLL_PAID"]


def test_loan_grant_installment_and_payment_reversal_are_posted(bootstrapped_conn):
    """Préstamo: Dr 1145 / Cr Caja; su abono en nómina acredita 1145; revertir el
    pago contabilizado deja la nómina en cero sin borrar asientos."""
    from backend.application.use_cases.hr.payroll_adjustment_use_cases import (
        ReversePayrollPaymentUseCase,
    )
    from backend.application.use_cases.hr.payroll_inputs_use_cases import (
        GrantEmployeeLoanUseCase,
    )

    conn = bootstrapped_conn
    create_hr_schema(conn)
    auth = AuthorizationPolicy(_AllowAll())
    branch = new_uuid()
    employee_id = CreateEmployeeUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), employee_code="N-2", first_name="Luis",
        last_name="Mora", branch_id=branch, contract_type="PERMANENT",
        payment_frequency="WEEKLY", base_salary="0.00", daily_salary="300.00",
        hire_date=date(2025, 1, 1), operation_id=new_uuid()).entity_id
    assert GrantEmployeeLoanUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), employee_id=employee_id, kind="LOAN",
        principal="1000", installment="400", payment_method="CASH", reason="Emergencia",
        operation_id=new_uuid(), granted_on=date(2026, 7, 1)).success
    conn.execute("UPDATE hr_outbox SET created_at='2026-07-01T00:00:00+00:00'"
                 " WHERE event_name='EMPLOYEE_LOAN_GRANTED'")
    run_id = GeneratePayrollRunUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7), operation_id=new_uuid(), branch_id=branch,
        today=date(2026, 7, 16)).entity_id
    AuthorizePayrollRunUseCase(auth).execute(conn, actor_user_id=new_uuid(),
                                            payroll_run_id=run_id, operation_id=new_uuid())
    PayPayrollRunUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), payroll_run_id=run_id, payment_method="CASH",
        operation_id=new_uuid(), paid_at=datetime(2026, 7, 16, 18, 0, tzinfo=timezone.utc))
    bus = get_bus()
    wire_hr_finance(bus, conn)
    result = dispatch_hr_outbox(conn, bus)
    errors = conn.execute("SELECT event_name, last_error FROM hr_outbox WHERE last_error IS NOT NULL"
                          ).fetchall()
    assert result["failed"] == 0 and result["without_consumer"] == 0, errors
    assert _balance(conn, "1145") == Decimal("600.00")          # 1000 − 400
    assert _balance(conn, "1101") == Decimal("-2700.00")        # 1000 + 1700 neto
    assert _balance(conn, "6101") == Decimal("2100.00")
    assert ReversePayrollPaymentUseCase(auth).execute(
        conn, actor_user_id=new_uuid(), payroll_run_id=run_id, reason="Pago duplicado",
        operation_id=new_uuid()).success
    dispatch_hr_outbox(conn, bus)
    rows = conn.execute(
        "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
        " JOIN journal_entries je ON je.id=jl.journal_entry_id"
        " JOIN accounts a ON a.id=jl.account_id WHERE a.code='6101'").fetchall()
    assert sum(Decimal(d) - Decimal(c) for d, c in rows) == Decimal("0")
    assert _balance(conn, "1145") == Decimal("1000.00")   # el reverso devuelve el abono
