"""COUPON_EXPIRED — expiración trazable del cupón."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentExpiredAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class CouponExpiredHandler(InstrumentExpiredAdapter):
    event_name = "COUPON_EXPIRED"
    instrument_type = CommercialInstrumentType.PROMOTIONAL_COUPON
