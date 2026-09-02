"""CommercialInstrumentResult — the return type every Commercial
Instruments use case produces. Mirrors
backend/application/loyalty/result.py's shape exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.commercial_instruments.exceptions import (
    CommercialInstrumentDomainError,
    CouponAlreadyRedeemedError,
    CouponDefinitionNotFoundError,
    CouponExpiredError,
    CouponInactiveError,
    CouponNotEligibleError,
    CouponNotFoundError,
    InvalidCouponDefinitionError,
    InvalidCouponInstanceStateError,
    InvalidVoucherDefinitionError,
    InvalidVoucherInstanceStateError,
    InvalidVoucherTransactionAmountError,
    InvalidVoucherTransactionStateError,
    VoucherDefinitionNotFoundError,
    VoucherExpiredError,
    VoucherInactiveError,
    VoucherInsufficientBalanceError,
    VoucherNotFoundError,
    VoucherTransactionNotFoundError,
)
from backend.domain.loyalty.exceptions import (
    LoyaltyConfigurationError,
    LoyaltyPermissionDeniedError,
)


@dataclass(frozen=True, slots=True)
class CommercialInstrumentResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "CommercialInstrumentResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "CommercialInstrumentResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (LoyaltyPermissionDeniedError, "PERMISSION_DENIED"),
    (LoyaltyConfigurationError, "CONFIGURATION_ERROR"),
    (CouponDefinitionNotFoundError, "COUPON_DEFINITION_NOT_FOUND"),
    (InvalidCouponDefinitionError, "INVALID_COUPON_DEFINITION"),
    (CouponNotFoundError, "COUPON_NOT_FOUND"),
    (CouponInactiveError, "COUPON_INACTIVE"),
    (CouponExpiredError, "COUPON_EXPIRED"),
    (CouponNotEligibleError, "COUPON_NOT_ELIGIBLE"),
    (CouponAlreadyRedeemedError, "COUPON_ALREADY_REDEEMED"),
    (InvalidCouponInstanceStateError, "COUPON_INSTANCE_INVALID_STATE"),
    (VoucherDefinitionNotFoundError, "VOUCHER_DEFINITION_NOT_FOUND"),
    (InvalidVoucherDefinitionError, "INVALID_VOUCHER_DEFINITION"),
    (VoucherNotFoundError, "VOUCHER_NOT_FOUND"),
    (VoucherInactiveError, "VOUCHER_INACTIVE"),
    (VoucherExpiredError, "VOUCHER_EXPIRED"),
    (VoucherInsufficientBalanceError, "VOUCHER_INSUFFICIENT_BALANCE"),
    (InvalidVoucherInstanceStateError, "VOUCHER_INSTANCE_INVALID_STATE"),
    (InvalidVoucherTransactionAmountError, "INVALID_VOUCHER_TRANSACTION_AMOUNT"),
    (InvalidVoucherTransactionStateError, "VOUCHER_TRANSACTION_INVALID_STATE"),
    (VoucherTransactionNotFoundError, "VOUCHER_TRANSACTION_NOT_FOUND"),
)


def fail_from_domain_error(
    exc: CommercialInstrumentDomainError | Exception, *, operation_id: str | None = None,
) -> CommercialInstrumentResult:
    """Translate any typed domain exception (Commercial Instruments' own, or
    a shared LOY-1 security exception reused via `LoyaltyAuthorizationPolicy`)
    into a `CommercialInstrumentResult.fail()`."""
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return CommercialInstrumentResult.fail(str(exc), code, operation_id=operation_id)
