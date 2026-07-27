"""Shared adapters for commercial-instrument events (coupons, vouchers,
gift cards, store credit, promotional balances).

Every concrete handler file declares: the event name, the instrument type and
the payload field carrying the instrument identity. The heavy lifting lives in
``CommercialInstrumentProcessor``.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError


class InstrumentEventAdapter(FinanceEventHandler):
    instrument_type: CommercialInstrumentType
    instrument_id_field: str = "instrument_id"
    source_module: str = "promotions"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._processor = CommercialInstrumentProcessor()

    def _instrument_id(self, payload: dict) -> str:
        instrument_id = str(payload.get(self.instrument_id_field) or "")
        if not instrument_id:
            raise FinanceDomainError(
                f"{self.event_name} sin {self.instrument_id_field}"
            )
        return instrument_id


class InstrumentIssuedAdapter(InstrumentEventAdapter):
    """Issue/sell/grant: recognizes according to the instrument's nature."""

    value_field: str = "face_value"

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        face_value = self.money(payload, self.value_field, currency)
        settlement = None
        if payload.get("settlement_amount") not in (None, ""):
            settlement = self.money(payload, "settlement_amount", currency)
        self._processor.recognize(
            uow,
            instrument_type=self.instrument_type,
            source_module=str(payload.get("source_module") or self.source_module),
            source_instrument_id=self._instrument_id(payload),
            amount=face_value,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            customer_id=payload.get("customer_id"),
            branch_id=payload.get("branch_id"),
            program_id=payload.get("program_id"),
            campaign_id=payload.get("campaign_id"),
            funding_party=payload.get("funding_party"),
            expires_at=payload.get("expires_at"),
            settlement_amount=settlement,
        )


class InstrumentRedeemedAdapter(InstrumentEventAdapter):
    value_field: str = "redeemed_value"

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        amount = self.money(payload, self.value_field, currency)
        actual_cost = None
        if payload.get("actual_cost") not in (None, ""):
            actual_cost = self.money(payload, "actual_cost", currency)
        self._processor.redeem(
            uow,
            instrument_type=self.instrument_type,
            source_instrument_id=self._instrument_id(payload),
            amount=amount,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            redemption_id=payload.get("redemption_id"),
            actual_cost=actual_cost,
        )


class InstrumentExpiredAdapter(InstrumentEventAdapter):
    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        amount = None
        if payload.get("expired_value") not in (None, ""):
            amount = self.money(payload, "expired_value", currency)
        self._processor.expire(
            uow,
            instrument_type=self.instrument_type,
            source_instrument_id=self._instrument_id(payload),
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            amount=amount,
        )


class InstrumentReversedAdapter(InstrumentEventAdapter):
    def _handle(self, uow, payload: dict) -> None:
        self._processor.reverse(
            uow,
            instrument_type=self.instrument_type,
            source_instrument_id=self._instrument_id(payload),
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            reason=str(payload.get("reason") or f"Reverso {self.event_name}"),
        )
