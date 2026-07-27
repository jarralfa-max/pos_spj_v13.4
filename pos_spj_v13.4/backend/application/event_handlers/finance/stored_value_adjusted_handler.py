"""STORED_VALUE_ADJUSTED — saldos promocionales: nunca efectivo, nunca
mezclados con saldo reembolsable del cliente."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentIssuedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class StoredValueAdjustedHandler(InstrumentIssuedAdapter):
    event_name = "STORED_VALUE_ADJUSTED"
    instrument_type = CommercialInstrumentType.PROMOTIONAL_BALANCE
