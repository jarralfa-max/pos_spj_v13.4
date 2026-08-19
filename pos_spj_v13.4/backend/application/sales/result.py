"""SaleResult — the return type every Sales/POS use case produces. Mirrors
backend/application/customers/result.py's `CustomerResult` shape exactly
(this repo's newer, richer per-context Result convention — no shared base
class exists for it anywhere in the repo, confirmed by research; each
context defines its own copy of the same shape).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.sales.exceptions import (
    CreditNotAuthorizedError,
    DiscountNotAllowedError,
    InventoryReservationFailedError,
    InvalidMoneyValueError,
    InvalidQuantityError,
    InvoiceAlreadyPendingError,
    InvoiceRequestNotAllowedError,
    InvoiceRequestNotFoundError,
    InvoiceTransitionNotAllowedError,
    LoyaltyRedemptionNotAvailableError,
    ReceiptNotAvailableError,
    ReturnQuantityExceededError,
    SaleCancellationNotAllowedError,
    SaleCustomerNotFoundError,
    SaleEmptyCartError,
    SaleInvalidStateError,
    SaleLineNotFoundError,
    SaleNotFoundError,
    SalePaymentIncompleteError,
    SalesConfigurationError,
    SalesDomainError,
    SalesPermissionDeniedError,
    SaleResumeNotAllowedError,
    SaleReturnNotAllowedError,
    SaleReversalNotAllowedError,
    SalesSegregationOfDutiesError,
    SaleSuspensionLimitError,
    ScanCodeNotResolvedError,
)


@dataclass(frozen=True, slots=True)
class SaleResult:
    success: bool
    message: str = ""
    operation_id: str | None = None
    entity_id: str | None = None
    error_code: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "", *, entity_id: str | None = None,
           operation_id: str | None = None, **data: Any) -> "SaleResult":
        return cls(True, message, operation_id, entity_id, None, dict(data))

    @classmethod
    def fail(cls, message: str, error_code: str, *,
             operation_id: str | None = None, **data: Any) -> "SaleResult":
        return cls(False, message, operation_id, None, error_code, dict(data))


_ERROR_CODES: tuple[tuple[type[SalesDomainError], str], ...] = (
    (SalesPermissionDeniedError, "PERMISSION_DENIED"),
    (SalesConfigurationError, "CONFIGURATION_ERROR"),
    (SalesSegregationOfDutiesError, "SEGREGATION_OF_DUTIES"),
    (SaleNotFoundError, "NOT_FOUND"),
    (SaleLineNotFoundError, "LINE_NOT_FOUND"),
    (SaleInvalidStateError, "INVALID_STATE"),
    (InvalidQuantityError, "INVALID_QUANTITY"),
    (InvalidMoneyValueError, "INVALID_MONEY"),
    (SaleEmptyCartError, "EMPTY_CART"),
    (DiscountNotAllowedError, "DISCOUNT_NOT_ALLOWED"),
    (SaleSuspensionLimitError, "SUSPENSION_LIMIT"),
    (SaleResumeNotAllowedError, "RESUME_NOT_ALLOWED"),
    (SaleCancellationNotAllowedError, "CANCELLATION_NOT_ALLOWED"),
    # SALES-9: this mapping was missing when InventoryReservationFailedError
    # was introduced — it silently fell through to the generic "VALIDATION"
    # fallback. Found while adding SaleCustomerNotFoundError in SALES-10 and
    # noticing the same omission pattern; fixed here, not a new bug.
    (InventoryReservationFailedError, "INVENTORY_RESERVATION_FAILED"),
    (SaleCustomerNotFoundError, "CUSTOMER_NOT_FOUND"),
    (ScanCodeNotResolvedError, "SCAN_CODE_NOT_RESOLVED"),
    (SalePaymentIncompleteError, "PAYMENT_INCOMPLETE"),
    (CreditNotAuthorizedError, "CREDIT_NOT_AUTHORIZED"),
    (LoyaltyRedemptionNotAvailableError, "LOYALTY_REDEMPTION_UNAVAILABLE"),
    (SaleReturnNotAllowedError, "RETURN_NOT_ALLOWED"),
    (ReturnQuantityExceededError, "RETURN_QUANTITY_EXCEEDED"),
    (SaleReversalNotAllowedError, "REVERSAL_NOT_ALLOWED"),
    (ReceiptNotAvailableError, "RECEIPT_NOT_AVAILABLE"),
    (InvoiceAlreadyPendingError, "INVOICE_ALREADY_PENDING"),
    (InvoiceRequestNotAllowedError, "INVOICE_REQUEST_NOT_ALLOWED"),
    (InvoiceRequestNotFoundError, "INVOICE_REQUEST_NOT_FOUND"),
    (InvoiceTransitionNotAllowedError, "INVOICE_TRANSITION_NOT_ALLOWED"),
)


def fail_from_domain_error(exc: SalesDomainError, *, operation_id: str | None = None) -> SaleResult:
    """Translate any typed Sales domain exception into a `SaleResult.fail()`
    — one mapping table instead of a bespoke try/except per use case."""
    code = next((code for cls, code in _ERROR_CODES if isinstance(exc, cls)), "VALIDATION")
    return SaleResult.fail(str(exc), code, operation_id=operation_id)
