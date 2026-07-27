"""COUPON_REDEEMED — reconoce el contra-ingreso en el momento del canje."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentRedeemedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class CouponRedeemedHandler(InstrumentRedeemedAdapter):
    event_name = "COUPON_REDEEMED"
    instrument_type = CommercialInstrumentType.PROMOTIONAL_COUPON
