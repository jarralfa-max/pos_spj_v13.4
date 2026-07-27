"""GIFT_CARD_SOLD — vender una tarjeta genera PASIVO, no ingreso:
Dr caja/banco/procesador, Cr obligación por tarjetas de regalo."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentIssuedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class GiftCardSoldHandler(InstrumentIssuedAdapter):
    event_name = "GIFT_CARD_SOLD"
    instrument_type = CommercialInstrumentType.GIFT_CARD
