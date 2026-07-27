"""CASH_SHIFT_CLOSED handler — Treasury consumes cash-register cuts.

Caja owns the shift (apertura, arqueo, corte Z); Finance recognizes the
economic result: counted cash moved to general cash and over/short differences
posted explicitly — never silently absorbed.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid


class CashShiftClosedHandler(FinanceEventHandler):
    event_name = "CASH_SHIFT_CLOSED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        shift_id = str(payload.get("shift_id") or "")
        if not shift_id:
            raise FinanceDomainError("CASH_SHIFT_CLOSED sin shift_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")

        expected_cash = self.money(payload, "expected_cash", currency)
        counted_cash = self.money(payload, "counted_cash", currency)
        difference = counted_cash.subtract(expected_cash)

        profile = self.resolve_profile(uow, "CASH_SHIFT", entry_date)
        register_account = profile.account_for("cash_account_id")       # POS register
        general_cash = self.resolve_profile(uow, "CAPITAL", entry_date).account_for("cash_account_id")

        lines: list[LineSpec] = []
        if counted_cash.is_positive():
            lines.append(LineSpec(general_cash, debit=counted_cash,
                                  description=f"Efectivo contado corte {shift_id[:8]}"))
        if difference.is_negative():
            lines.append(LineSpec(profile.account_for("cash_over_short_account_id"),
                                  debit=difference.abs(), description="Faltante de caja"))
        if expected_cash.is_positive():
            lines.append(LineSpec(register_account, credit=expected_cash,
                                  description=f"Vaciado de caja registradora {shift_id[:8]}"))
        if difference.is_positive():
            lines.append(LineSpec(profile.account_for("breakage_income_account_id"),
                                  credit=difference, description="Sobrante de caja"))
        if not lines:
            return

        self._engine.post(
            uow, JournalType.CASH, entry_date, f"Corte de caja {shift_id[:8]}",
            PostingReference("cash", shift_id, PostingPurpose.CASH_SHIFT_CLOSE,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
        )
        if not difference.is_zero():
            uow.outbox.enqueue(
                event_id=new_uuid(),
                event_name="CASH_DIFFERENCE_DETECTED",
                payload_json=(
                    '{"shift_id": "%s", "difference": "%s", "currency_code": "%s"}'
                    % (shift_id, difference.to_string(), currency)
                ),
                operation_id=str(payload["operation_id"]),
            )
