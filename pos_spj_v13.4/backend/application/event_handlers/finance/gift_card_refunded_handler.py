"""GIFT_CARD_REFUNDED — reverso espejo del reconocimiento; el original es inmutable."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentReversedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class GiftCardRefundedHandler(InstrumentReversedAdapter):
    event_name = "GIFT_CARD_REFUNDED"
    instrument_type = CommercialInstrumentType.GIFT_CARD
