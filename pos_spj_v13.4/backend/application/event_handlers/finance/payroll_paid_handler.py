"""PAYROLL_PAID handler — exactly one journal entry per payroll payment.

Finance consumes only the canonical HR event; there is no direct payroll
route into the ledger and double processing is structurally impossible
(idempotency by event_id, operation_id and payroll_run_id).
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class PayrollPaidHandler(FinanceEventHandler):
    event_name = "PAYROLL_PAID"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        payroll_run_id = str(payload.get("payroll_run_id") or "")
        if not payroll_run_id:
            raise FinanceDomainError("PAYROLL_PAID requiere payroll_run_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")

        gross_salaries = self.money(payload, "gross_salaries", currency)
        social_security = self.money(payload, "social_security", currency, required=False)
        net_paid = self.money(payload, "net_paid", currency)
        loan_deductions = self.money(payload, "loan_deductions", currency, required=False)
        withholdings = gross_salaries.add(social_security).subtract(net_paid).subtract(
            loan_deductions)
        if withholdings.is_negative():
            raise FinanceDomainError(
                "PAYROLL_PAID: el neto pagado excede sueldos + cargas sociales"
            )

        profile = self.resolve_profile(uow, "PAYROLL", entry_date)
        lines = [
            LineSpec(profile.account_for("salary_expense_account_id"), debit=gross_salaries,
                     description=f"Sueldos nómina {payroll_run_id[:8]}"),
        ]
        if social_security.is_positive():
            lines.append(LineSpec(profile.account_for("expense_account_id"),
                                  debit=social_security,
                                  description="Cargas sociales (IMSS)"))
        method = str(payload.get("payment_method") or "BANK_TRANSFER").upper()
        lines.append(LineSpec(self._payment_account(uow, profile, method, entry_date),
                              credit=net_paid,
                              description=f"Pago neto de nómina ({method})"))
        if loan_deductions.is_positive():
            # Abono a préstamos/anticipos: baja la cuenta por cobrar al empleado,
            # no es una retención por enterar.
            lines.append(LineSpec(self._employee_receivable(uow, profile, entry_date),
                                  credit=loan_deductions,
                                  description="Abono a préstamos y anticipos de empleados"))
        if withholdings.is_positive():
            lines.append(LineSpec(
                profile.account_for("social_security_payable_account_id"),
                credit=withholdings, description="Retenciones y cargas por enterar"))

        self._engine.post(
            uow, JournalType.PAYROLL, entry_date, f"Nómina pagada {payroll_run_id[:8]}",
            PostingReference("hr", payroll_run_id, PostingPurpose.PAYROLL,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
        )

    def _role(self, uow, profile, role: str, entry_date) -> str:
        """El rol en el perfil PAYROLL; si el perfil es previo a 2026-10-14 y no
        lo trae, el del perfil EMPLOYEE_LOAN (se agrega al arrancar)."""
        account_id = (getattr(profile, "accounts", None) or {}).get(role)
        if account_id:
            return account_id
        return self.resolve_profile(uow, "EMPLOYEE_LOAN", entry_date).account_for(role)

    def _employee_receivable(self, uow, profile, entry_date) -> str:
        return self._role(uow, profile, "employee_receivable_account_id", entry_date)

    def _payment_account(self, uow, profile, method: str, entry_date) -> str:
        """Auditoría RRHH HR-29: el EFECTIVO acredita caja, no bancos (antes todo
        pago de nómina abonaba la cuenta 1110). Transferencia y cheque, bancos.
        Perfiles sembrados antes del 2026-10-14 no traen el rol de caja: se usa
        la cuenta 1101 (Caja) del catálogo."""
        if method == "CASH":
            return self._role(uow, profile, "cash_account_id", entry_date)
        return profile.account_for("bank_account_id")
