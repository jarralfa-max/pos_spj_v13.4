"""CommercialObligation entity — financial recognition of commercial instruments.

Finance never owns the operational instrument (points, coupons, vouchers, gift
cards). ``source_instrument_id`` references the identity inside the owning
bounded context. This entity tracks only the recognized economic effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import (
    CommercialInstrumentType,
    CommercialObligationStatus,
    RecognitionBasis,
)
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    ObligationAmountError,
    ObligationStateError,
)
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

_REDEEMABLE = (
    CommercialObligationStatus.OPEN,
    CommercialObligationStatus.PARTIALLY_REDEEMED,
    # A NO_INITIAL_RECOGNITION instrument (promotional coupon) is redeemable
    # and expirable while pending: its effect posts only at redemption time.
    CommercialObligationStatus.PENDING_RECOGNITION,
)


@dataclass(slots=True)
class CommercialObligation:
    id: str
    instrument_type: CommercialInstrumentType
    source_module: str
    source_instrument_id: str
    recognition_basis: RecognitionBasis
    original_amount: Money
    recognized_amount: Money
    redeemed_amount: Money
    released_amount: Money
    operation_id: str
    customer_id: str | None = None
    branch_id: str | None = None
    status: CommercialObligationStatus = CommercialObligationStatus.OPEN
    issued_at: str | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def recognize(
        cls,
        instrument_type: CommercialInstrumentType,
        source_module: str,
        source_instrument_id: str,
        recognition_basis: RecognitionBasis,
        original_amount: Money,
        operation_id: str,
        *,
        recognized_amount: Money | None = None,
        customer_id: str | None = None,
        branch_id: str | None = None,
        issued_at: str | None = None,
        expires_at: str | None = None,
    ) -> "CommercialObligation":
        if not source_module or not source_instrument_id:
            raise FinanceDomainError(
                "CommercialObligation requires source_module and source_instrument_id"
            )
        if original_amount.is_negative():
            raise FinanceDomainError("CommercialObligation.original_amount must not be negative")
        recognized = recognized_amount if recognized_amount is not None else original_amount
        if recognized.is_negative():
            raise FinanceDomainError("CommercialObligation.recognized_amount must not be negative")
        zero = Money.zero(original_amount.currency_code)
        status = (
            CommercialObligationStatus.OPEN
            if recognition_basis is not RecognitionBasis.NO_INITIAL_RECOGNITION
            else CommercialObligationStatus.PENDING_RECOGNITION
        )
        return cls(
            id=new_uuid(),
            instrument_type=instrument_type,
            source_module=source_module,
            source_instrument_id=source_instrument_id,
            recognition_basis=recognition_basis,
            original_amount=original_amount,
            recognized_amount=recognized,
            redeemed_amount=zero,
            released_amount=zero,
            operation_id=operation_id,
            customer_id=customer_id,
            branch_id=branch_id,
            status=status,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    @property
    def outstanding_amount(self) -> Money:
        return (self.recognized_amount
                .subtract(self.redeemed_amount)
                .subtract(self.released_amount))

    def increase_recognition(self, amount: Money) -> None:
        """Reload/top-up (e.g. gift card reload) increases the recognized obligation."""
        if self.status not in _REDEEMABLE and self.status is not CommercialObligationStatus.PENDING_RECOGNITION:
            raise ObligationStateError(f"Cannot increase a {self.status.value} obligation")
        if not amount.is_positive():
            raise FinanceDomainError("Recognition increase must be positive")
        self.recognized_amount = self.recognized_amount.add(amount)
        if self.status is CommercialObligationStatus.PENDING_RECOGNITION:
            self.status = CommercialObligationStatus.OPEN
        self.updated_at = _utcnow()

    def redeem(self, amount: Money) -> None:
        if self.status not in _REDEEMABLE:
            raise ObligationStateError(
                f"Cannot redeem obligation in status {self.status.value} "
                f"(instrument={self.source_instrument_id})"
            )
        if not amount.is_positive():
            raise FinanceDomainError("Redemption amount must be positive")
        if amount > self.outstanding_amount:
            raise ObligationAmountError(
                f"Redemption {amount.to_string()} exceeds outstanding {self.outstanding_amount.to_string()}"
            )
        self.redeemed_amount = self.redeemed_amount.add(amount)
        self.status = (CommercialObligationStatus.REDEEMED if self.outstanding_amount.is_zero()
                       else CommercialObligationStatus.PARTIALLY_REDEEMED)
        self.updated_at = _utcnow()

    def release_by_expiration(self, amount: Money | None = None) -> Money:
        """Expiration never deletes the obligation: it releases the outstanding
        balance (breakage) and returns the released amount for posting."""
        if self.status not in _REDEEMABLE:
            raise ObligationStateError(
                f"Cannot expire obligation in status {self.status.value}"
            )
        to_release = amount if amount is not None else self.outstanding_amount
        if to_release.is_negative() or to_release > self.outstanding_amount:
            raise ObligationAmountError("Release exceeds the outstanding obligation")
        self.released_amount = self.released_amount.add(to_release)
        self.status = CommercialObligationStatus.EXPIRED
        self.updated_at = _utcnow()
        return to_release

    def reverse(self) -> Money:
        """Full reversal (e.g. sale cancelled). Returns the amount to unwind."""
        if self.status in (CommercialObligationStatus.REVERSED, CommercialObligationStatus.CANCELLED):
            raise ObligationStateError(f"Obligation already {self.status.value}")
        outstanding = self.outstanding_amount
        self.released_amount = self.released_amount.add(outstanding)
        self.status = CommercialObligationStatus.REVERSED
        self.updated_at = _utcnow()
        return outstanding

    def cancel(self) -> None:
        if self.redeemed_amount.is_positive():
            raise ObligationStateError("Cannot cancel an obligation with redemptions; reverse it")
        self.status = CommercialObligationStatus.CANCELLED
        self.released_amount = self.released_amount.add(self.outstanding_amount)
        self.updated_at = _utcnow()
