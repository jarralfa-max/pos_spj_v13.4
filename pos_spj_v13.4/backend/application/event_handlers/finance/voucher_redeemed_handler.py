"""VOUCHER_REDEEMED — cancela la obligación por vales pendientes."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentRedeemedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class VoucherRedeemedHandler(InstrumentRedeemedAdapter):
    event_name = "VOUCHER_REDEEMED"
    instrument_type = CommercialInstrumentType.REFUND_VOUCHER
