"""RR. HH. → Finanzas: préstamos a empleados y reverso de un pago de nómina
(2026-10-14).

* ``EMPLOYEE_LOAN_GRANTED`` — entregar un préstamo/anticipo mueve dinero: Dr
  Préstamos y anticipos a empleados (1145) / Cr Caja (1101) o Bancos (1110). Los
  abonos llegan después en cada PAYROLL_PAID (``loan_deductions``) y abonan 1145.
* ``PAYROLL_PAYMENT_REVERSED`` — un pago de nómina registrado por error se
  revierte con el asiento espejo del original (no se borra nada).

Ambos idempotentes por ``event_id`` (``FinanceEventHandler``) y por referencia
de contabilización.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class EmployeeLoanGrantedHandler(FinanceEventHandler):
    event_name = "EMPLOYEE_LOAN_GRANTED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        loan_id = str(payload.get("loan_id") or "")
        if not loan_id:
            raise FinanceDomainError("EMPLOYEE_LOAN_GRANTED requiere loan_id")
        currency = self.currency(payload)
        amount = self.money(payload, "amount", currency)
        if not amount.is_positive():
            raise FinanceDomainError("El préstamo debe ser mayor que cero")
        method = str(payload.get("payment_method") or "CASH").upper()
        entry_date = self.event_date(payload)
        profile = self.resolve_profile(uow, "EMPLOYEE_LOAN", entry_date)
        source = profile.account_for("cash_account_id" if method == "CASH"
                                     else "bank_account_id")
        kind = "Anticipo" if payload.get("kind") == "ADVANCE" else "Préstamo"
        self._engine.post(
            uow, JournalType.GENERAL, entry_date,
            f"{kind} a empleado {str(payload.get('employee_code') or '')}".strip(),
            PostingReference("hr", loan_id, PostingPurpose.EMPLOYEE_LOAN,
                             str(payload["operation_id"])),
            [LineSpec(profile.account_for("employee_receivable_account_id"), debit=amount,
                      description=f"{kind} a empleado"),
             LineSpec(source, credit=amount, description=f"Entrega ({method})")],
            currency_code=currency, branch_id=payload.get("branch_id"))


class PayrollPaymentReversedHandler(FinanceEventHandler):
    event_name = "PAYROLL_PAYMENT_REVERSED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        run_id = str(payload.get("payroll_run_id") or "")
        if not run_id:
            raise FinanceDomainError("PAYROLL_PAYMENT_REVERSED requiere payroll_run_id")
        entry = uow.journal_entries.find_by_posting_reference("hr", run_id, PostingPurpose.PAYROLL)
        if entry is None:
            # La nómina aún no se había contabilizado: no hay nada que revertir.
            # (Si el PAYROLL_PAID sigue pendiente se descarta en el despachador.)
            return
        if entry.reversed_by_entry_id:
            return
        self._engine.reverse(
            uow, entry, self.event_date(payload),
            str(payload.get("reason") or "Reverso de pago de nómina"),
            f"{payload['operation_id']}:payroll-reversal",
            created_by=payload.get("reversed_by_user_id"))
