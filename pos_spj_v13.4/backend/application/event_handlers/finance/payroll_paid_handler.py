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
        withholdings = gross_salaries.add(social_security).subtract(net_paid)
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
        lines.append(LineSpec(profile.account_for("bank_account_id"), credit=net_paid,
                              description="Pago neto de nómina"))
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
