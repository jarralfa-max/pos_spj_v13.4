"""VOUCHER_EXPIRED — libera la obligación a ingreso por expiración."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentExpiredAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class VoucherExpiredHandler(InstrumentExpiredAdapter):
    event_name = "VOUCHER_EXPIRED"
    instrument_type = CommercialInstrumentType.REFUND_VOUCHER
