"""CASH-21 consumers owned by Finance and Treasury.

Custody events are acknowledged without creating a second economic effect.
Only a confirmed bank deposit posts a transfer from general cash to bank.
"""
from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import validate_uuidv7


def _uuid(payload: dict, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise FinanceDomainError(f"Cash/Treasury event missing {key}")
    try:
        validate_uuidv7(value)
    except ValueError as exc:
        raise FinanceDomainError(f"Cash/Treasury event has invalid {key}") from exc
    return value


class CashDifferenceDetectedHandler(FinanceEventHandler):
    event_name = "CASH_DIFFERENCE_DETECTED"

    def _handle(self, uow, payload: dict) -> None:
        _uuid(payload, "difference_id")
        _uuid(payload, "shift_id")
        self.money(payload, "amount", self.currency(payload))
        # The Z-cut posting already includes over/short. This event supplies
        # classification and workflow trace only, preventing double posting.


class CashRefundProcessedHandler(FinanceEventHandler):
    event_name = "CASH_REFUND_PROCESSED"

    def _handle(self, uow, payload: dict) -> None:
        _uuid(payload, "refund_id"); _uuid(payload, "sale_id")
        self.money(payload, "cash_amount", self.currency(payload), required=False)
        if payload.get("finance_event") != "SALE_REFUNDED":
            raise FinanceDomainError("Cash refund must reference SALE_REFUNDED")
        # Sales owns revenue/tax reversal. Cash only confirms physical settlement.


class CashHandoverReceivedHandler(FinanceEventHandler):
    event_name = "CASH_HANDOVER_RECEIVED"

    def _handle(self, uow, payload: dict) -> None:
        _uuid(payload, "handover_id"); _uuid(payload, "shift_id")
        amount = self.money(payload, "received_amount", self.currency(payload))
        if not amount.is_positive() or payload.get("treasury_transfer_required") is not True:
            raise FinanceDomainError("Treasury handover must be matched and positive")
        # Register -> general-cash custody is already represented by the Z cut.


class CashDepositPreparedHandler(FinanceEventHandler):
    event_name = "CASH_DEPOSIT_PREPARED"

    def _handle(self, uow, payload: dict) -> None:
        _uuid(payload, "deposit_id")
        amount = self.money(payload, "amount", self.currency(payload))
        if not amount.is_positive():
            raise FinanceDomainError("Prepared deposit must be positive")
        # Cash prepares a deposit package only. Treasury owns bank confirmation
        # and Finance posts only TREASURY_CASH_DEPOSIT_CONFIRMED.


class TreasuryCashDepositConfirmedHandler(FinanceEventHandler):
    event_name = "TREASURY_CASH_DEPOSIT_CONFIRMED"

    def __init__(self, connection) -> None:
        super().__init__(connection); self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        deposit_id = _uuid(payload, "deposit_id")
        amount = self.money(payload, "amount", self.currency(payload))
        if not amount.is_positive():
            raise FinanceDomainError("Confirmed deposit must be positive")
        entry_date = self.event_date(payload)
        cash = self.resolve_profile(uow, "CAPITAL", entry_date).account_for("cash_account_id")
        bank = self.resolve_profile(uow, "CAPITAL", entry_date).account_for("bank_account_id")
        self._engine.post(
            uow, JournalType.BANK, entry_date, f"Depósito de efectivo {deposit_id[:8]}",
            PostingReference("treasury", deposit_id, PostingPurpose.CASH_DEPOSIT,
                             str(payload["operation_id"])),
            [LineSpec(bank, debit=amount, description="Entrada a banco"),
             LineSpec(cash, credit=amount, description="Salida de caja general")],
            currency_code=self.currency(payload), branch_id=payload.get("branch_id"),
        )
