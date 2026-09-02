"""Domain exceptions for the Commercial Instruments bounded context
(coupons/vouchers — LOY-12+, master prompt §66)."""

from __future__ import annotations


class CommercialInstrumentDomainError(Exception):
    """Base for Commercial Instruments rule violations."""


class InvalidCouponDefinitionError(CommercialInstrumentDomainError):
    """A coupon definition's configuration is invalid (missing code/name,
    non-positive benefit_value where required, non-Decimal amounts)."""


class CouponDefinitionNotFoundError(CommercialInstrumentDomainError):
    """No CouponDefinition with the given id/code exists."""


class CouponNotFoundError(CommercialInstrumentDomainError):
    """No CouponInstance with the given id/code exists — master prompt
    §66's own literal name."""


class CouponInactiveError(CommercialInstrumentDomainError):
    """The coupon exists but is not usable right now (not ACTIVE) — master
    prompt §66's own literal name."""


class CouponExpiredError(CommercialInstrumentDomainError):
    """The coupon's validity window has passed — master prompt §66's own
    literal name."""


class CouponNotEligibleError(CommercialInstrumentDomainError):
    """The coupon exists and is active but does not apply to this
    customer/sale (e.g. a PERSONALIZED coupon issued to someone else) —
    master prompt §66's own literal name."""


class CouponAlreadyRedeemedError(CommercialInstrumentDomainError):
    """The coupon has already been redeemed — master prompt §66's own
    literal name."""


class InvalidCouponInstanceStateError(CommercialInstrumentDomainError):
    """The requested transition is not valid for the coupon instance's
    current status."""


# ── LOY-13: vales ────────────────────────────────────────────────────────

class InvalidVoucherDefinitionError(CommercialInstrumentDomainError):
    """A voucher definition's configuration is invalid (missing code/name)."""


class VoucherDefinitionNotFoundError(CommercialInstrumentDomainError):
    """No VoucherDefinition with the given id exists."""


class VoucherNotFoundError(CommercialInstrumentDomainError):
    """No VoucherInstance with the given id/code exists — master prompt
    §66's own literal name."""


class VoucherInactiveError(CommercialInstrumentDomainError):
    """The voucher exists but is not usable right now — master prompt
    §66's own literal name."""


class VoucherExpiredError(CommercialInstrumentDomainError):
    """The voucher's validity window has passed — master prompt §66's own
    literal name."""


class VoucherInsufficientBalanceError(CommercialInstrumentDomainError):
    """A redeem/reserve was attempted for more than the voucher's current
    balance — master prompt §66's own literal name."""


class InvalidVoucherInstanceStateError(CommercialInstrumentDomainError):
    """The requested transition is not valid for the voucher instance's
    current status."""


class InvalidVoucherTransactionAmountError(CommercialInstrumentDomainError):
    """``amount`` is missing, non-Decimal, zero, or has the wrong sign for
    its ``transaction_type``."""


class InvalidVoucherTransactionStateError(CommercialInstrumentDomainError):
    """The requested status transition is not valid for the voucher
    transaction's current status."""


class VoucherTransactionNotFoundError(CommercialInstrumentDomainError):
    """No VoucherTransaction with the given id/operation_id exists."""
