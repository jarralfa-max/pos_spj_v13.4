"""VOUCHER_ISSUED — un vale por devolución SÍ es obligación real con el cliente."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentIssuedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class VoucherIssuedHandler(InstrumentIssuedAdapter):
    event_name = "VOUCHER_ISSUED"
    instrument_type = CommercialInstrumentType.REFUND_VOUCHER
