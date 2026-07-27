"""GIFT_CARD_REDEEMED — al canjear: Dr obligación, Cr ingreso (e impuestos)."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentRedeemedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class GiftCardRedeemedHandler(InstrumentRedeemedAdapter):
    event_name = "GIFT_CARD_REDEEMED"
    instrument_type = CommercialInstrumentType.GIFT_CARD
