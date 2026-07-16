"""Commercial instrument posting policy — how each instrument type is recognized.

Instruments are NOT all equal:
- promotional/discount coupons usually create no liability at issuance;
- refund vouchers and gift cards create a real customer liability;
- third-party funded coupons create a receivable against the funding party;
- promotional balances are never cash and never mix with refundable balances.
"""

from __future__ import annotations

from backend.domain.finance.enums import CommercialInstrumentType, RecognitionBasis
from backend.domain.finance.exceptions import FinanceDomainError

#: Default recognition basis at issuance per instrument type.
DEFAULT_RECOGNITION_BASIS: dict[CommercialInstrumentType, RecognitionBasis] = {
    CommercialInstrumentType.LOYALTY_POINTS: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.PROMOTIONAL_COUPON: RecognitionBasis.NO_INITIAL_RECOGNITION,
    CommercialInstrumentType.DISCOUNT_COUPON: RecognitionBasis.NO_INITIAL_RECOGNITION,
    CommercialInstrumentType.REFUND_VOUCHER: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.STORE_CREDIT: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.GIFT_CARD: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.PREPAID_VOUCHER: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.PROMOTIONAL_BALANCE: RecognitionBasis.PROMOTIONAL_EXPENSE,
    CommercialInstrumentType.CUSTOMER_WALLET: RecognitionBasis.LIABILITY,
    CommercialInstrumentType.THIRD_PARTY_VOUCHER: RecognitionBasis.THIRD_PARTY_RECEIVABLE,
}

#: Instrument types whose issuance requires cash/bank settlement (sold instruments).
SOLD_INSTRUMENTS = frozenset({
    CommercialInstrumentType.GIFT_CARD,
    CommercialInstrumentType.PREPAID_VOUCHER,
})

#: Instrument types that must never be treated as cash or refundable balance.
NON_CASH_INSTRUMENTS = frozenset({
    CommercialInstrumentType.PROMOTIONAL_BALANCE,
    CommercialInstrumentType.LOYALTY_POINTS,
    CommercialInstrumentType.PROMOTIONAL_COUPON,
    CommercialInstrumentType.DISCOUNT_COUPON,
})


class CommercialInstrumentPostingPolicy:
    def recognition_basis_for(
        self,
        instrument_type: CommercialInstrumentType,
        *,
        funding_party: str | None = None,
        override: RecognitionBasis | None = None,
    ) -> RecognitionBasis:
        """Resolve the recognition basis. A posting profile may override the default,
        but promotional balances can never become cash-like liabilities implicitly."""
        if override is not None:
            self._validate_override(instrument_type, override)
            return override
        if funding_party:
            return RecognitionBasis.THIRD_PARTY_RECEIVABLE
        try:
            return DEFAULT_RECOGNITION_BASIS[instrument_type]
        except KeyError as exc:
            raise FinanceDomainError(f"No recognition basis for {instrument_type}") from exc

    def requires_liability_at_issuance(self, instrument_type: CommercialInstrumentType) -> bool:
        return DEFAULT_RECOGNITION_BASIS[instrument_type] is RecognitionBasis.LIABILITY

    def is_sold_instrument(self, instrument_type: CommercialInstrumentType) -> bool:
        return instrument_type in SOLD_INSTRUMENTS

    def must_not_be_cash(self, instrument_type: CommercialInstrumentType) -> bool:
        return instrument_type in NON_CASH_INSTRUMENTS

    @staticmethod
    def _validate_override(instrument_type: CommercialInstrumentType,
                           override: RecognitionBasis) -> None:
        if (instrument_type in NON_CASH_INSTRUMENTS
                and override is RecognitionBasis.LIABILITY
                and instrument_type is not CommercialInstrumentType.LOYALTY_POINTS):
            raise FinanceDomainError(
                f"{instrument_type.value} cannot be overridden to a cash-like LIABILITY basis; "
                "promotional value is not customer money"
            )
