"""Canonical adapter from Cash event envelopes to Finance-owned handlers."""
from __future__ import annotations

from backend.application.event_handlers.finance.cash_shift_closed_handler import CashShiftClosedHandler
from backend.application.event_handlers.finance.cash_treasury_handlers import (
    CashDifferenceDetectedHandler, CashHandoverReceivedHandler,
    CashRefundProcessedHandler, TreasuryCashDepositConfirmedHandler,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import validate_uuidv7


class CashFinanceEventRouter:
    def __init__(self, connection) -> None:
        self._handlers = {
            "CASH_Z_CUT_GENERATED": CashShiftClosedHandler(connection),
            "CASH_DIFFERENCE_DETECTED": CashDifferenceDetectedHandler(connection),
            "CASH_REFUND_PROCESSED": CashRefundProcessedHandler(connection),
            "CASH_HANDOVER_RECEIVED": CashHandoverReceivedHandler(connection),
            "TREASURY_CASH_DEPOSIT_CONFIRMED": TreasuryCashDepositConfirmedHandler(connection),
        }

    def handle(self, event: dict) -> None:
        event_name = str(event.get("event_name") or "")
        handler = self._handlers.get(event_name)
        if handler is None:
            raise FinanceDomainError(f"Unsupported Cash/Finance event: {event_name}")
        try:
            for key in ("event_id", "operation_id", "entity_id", "branch_id"):
                validate_uuidv7(str(event.get(key) or ""))
        except ValueError as exc:
            raise FinanceDomainError("Cash/Finance event requires canonical UUIDv7 ids") from exc
        inner = event.get("payload") or {}
        if not isinstance(inner, dict):
            raise FinanceDomainError("Cash event payload must be an object")
        payload = {**inner,
                   "event_id": event.get("event_id"),
                   "operation_id": event.get("operation_id"),
                   "branch_id": event.get("branch_id"),
                   "occurred_at": event.get("timestamp") or event.get("occurred_at"),
                   "currency_code": inner.get("currency_code", "MXN")}
        aliases = {"difference_id": event.get("entity_id"),
                   "refund_id": event.get("entity_id"),
                   "handover_id": event.get("entity_id"),
                   "deposit_id": event.get("entity_id")}
        for key, value in aliases.items():
            payload.setdefault(key, value)
        handler.handle(payload)
