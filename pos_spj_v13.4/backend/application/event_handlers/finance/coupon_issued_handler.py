"""COUPON_ISSUED — un cupón promocional normalmente NO genera pasivo al emitirse
(NO_INITIAL_RECOGNITION); uno financiado por tercero reconoce CxC al financiador."""

from __future__ import annotations

from backend.application.event_handlers.finance.instrument_event_adapters import (
    InstrumentIssuedAdapter,
)
from backend.domain.finance.enums import CommercialInstrumentType


class CouponIssuedHandler(InstrumentIssuedAdapter):
    event_name = "COUPON_ISSUED"
    instrument_type = CommercialInstrumentType.PROMOTIONAL_COUPON
