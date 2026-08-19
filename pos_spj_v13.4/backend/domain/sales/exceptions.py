"""Domain exceptions for the Sales/POS bounded context.

SALES-2 defined the security-related errors (permission, configuration, hot
authorization, segregation of duties) — mirrors
backend/domain/inventory/exceptions.py's own INV-1-equivalent phase.
SALES-3 adds the operational errors the Sale/SaleLine aggregate and its
policies raise (a subset of master prompt §64 — only the ones a pure domain
layer can actually detect without I/O; PricingUnavailableError,
InventoryReservationFailedError, PaymentDeclinedError etc. belong to later
phases that touch other bounded contexts).
"""

from __future__ import annotations


class SalesDomainError(Exception):
    """Base for Sales/POS rule violations."""


class SalesPermissionDeniedError(SalesDomainError):
    """The user lacks the granular permission the action requires."""


class SalesConfigurationError(SalesDomainError):
    """A security-sensitive component was built without its mandatory wiring
    (e.g. an authorization policy with no PermissionChecker). Fail closed:
    never allow an operation to proceed on an unconfigured authorization
    gate."""


class SalesSegregationOfDutiesError(SalesDomainError):
    """A hot authorization was attempted by the same user who requested the
    exception — a second pair of eyes is mandatory (master prompt §62:
    'cajero no autoriza su propio descuento protegido')."""


class InvalidSalesAuditFieldError(SalesDomainError):
    """A required audit/authorization field is missing or of the wrong type
    (e.g. a float where Decimal is required)."""


# ── SALES-3: operational errors (master prompt §64, domain-detectable subset) ──

class SaleInvalidStateError(SalesDomainError):
    """The requested transition/mutation is not valid for the Sale's current
    status (SaleStateInvalidError in the master prompt's vocabulary)."""


class SaleNotFoundError(SalesDomainError):
    """No Sale with the given id (or operation_id) exists."""


class SaleLineNotFoundError(SalesDomainError):
    """No line with the given id exists on this Sale."""


class InvalidQuantityError(SalesDomainError):
    """A quantity/weight is missing, non-Decimal, zero or negative where a
    positive value is required."""


class InvalidMoneyValueError(SalesDomainError):
    """A monetary value is missing, non-Decimal, or otherwise invalid
    (negative where not allowed, infinite, NaN)."""


class SaleEmptyCartError(SalesDomainError):
    """An operation that requires at least one line (checkout, suspend) was
    attempted on a Sale with none."""


class DiscountNotAllowedError(SalesDomainError):
    """A discount exceeds the unauthorized threshold and no valid
    authorization was provided (master prompt §25/§62)."""


class SaleSuspensionLimitError(SalesDomainError):
    """The workstation/cashier already holds the maximum number of
    concurrently suspended sales (master prompt §41)."""


class SaleResumeNotAllowedError(SalesDomainError):
    """A suspended sale cannot be resumed under the current cross-user/
    cross-workstation policy configuration (master prompt §41)."""


class SaleCancellationNotAllowedError(SalesDomainError):
    """A Sale cannot be cancelled from its current status — a paid Sale must
    be reversed, not cancelled (master prompt §42)."""


class InventoryReservationFailedError(SalesDomainError):
    """Inventory could not reserve/confirm/release stock for this Sale
    (insufficient stock, unknown reservation, or the reservation is no
    longer active) — master prompt §64, §20."""


class SaleCustomerNotFoundError(SalesDomainError):
    """The customer id given to `assign_customer`/a card scan does not
    exist in the Customer Master bounded context (§6/§21) — distinct from
    Customer Master's own internal `CustomerNotFoundError`, since Sales
    never imports that domain's exceptions directly (cross-context
    boundary, backend/infrastructure/integrations/sales_customer_client.py
    translates at the edge)."""


class ScanCodeNotResolvedError(SalesDomainError):
    """A scanned code (POS-12/§17) matched neither a sellable product nor a
    loyalty/customer card — the router has nothing to dispatch to."""


class SalePaymentIncompleteError(SalesDomainError):
    """POS-13/§30-36: `Sale.complete()` was attempted while the sum of
    recorded `SalePayment` amounts is still less than `SaleTotals.total` —
    a sale cannot complete on a partial payment; the caller must record
    more payment lines (cash/card/transfer/credit/Mercado Pago, any mix)
    first."""


class CreditNotAuthorizedError(SalesDomainError):
    """POS-13/§30-36: a CREDIT payment line was rejected by Customer
    Master's real credit validation (no credit authorized, limit exceeded,
    or customer not found) — distinct from `SaleCustomerNotFoundError`,
    since the customer may exist but simply not be authorized/have room for
    this amount."""


class LoyaltyRedemptionNotAvailableError(SalesDomainError):
    """POS-14/§38-41: a loyalty point redemption could not be applied — no
    customer assigned, the loyalty program is disabled, or the real
    `LoyaltyService` rejected the request (insufficient points, below the
    program's minimum redemption threshold)."""


class SaleReturnNotAllowedError(SalesDomainError):
    """POS-16/§42-44: a line return was attempted on a Sale whose status
    doesn't allow it (only COMPLETED/RETURNED_PARTIALLY do)."""


class ReturnQuantityExceededError(SalesDomainError):
    """POS-16/§42-44: the requested return quantity, added to whatever was
    already returned for this line, would exceed the quantity originally
    sold — mirrors the over-return guard `core/services/
    sales_reversal_service.py::refund_items` already enforces for the
    legacy path (`SUM(prior refunds)+new <= qty_vendida`)."""


class SaleReversalNotAllowedError(SalesDomainError):
    """POS-16/§42-44: a full reversal was attempted on a Sale whose status
    doesn't allow it — only a COMPLETED sale can be reversed (§42: a
    cancelled/already-returned/already-reversed sale cannot be reversed
    again)."""


class ReceiptNotAvailableError(SalesDomainError):
    """POS-17/§46: a receipt was requested for a Sale that never actually
    completed checkout (`completed_at` is still unset) — nothing was ever
    charged, so there is nothing real to print/reprint."""


class InvoiceRequestNotAllowedError(SalesDomainError):
    """POS-18/§46/§15: an invoice was requested for a Sale whose status
    doesn't allow it (only a completed, non-reversed sale can be
    invoiced), or with a missing/invalid `tax_identifier`."""


class InvoiceAlreadyPendingError(SalesDomainError):
    """POS-18: a new invoice was requested while this Sale already has a
    REQUESTED invoice awaiting an outcome — must be resolved (issued/error)
    before a second attempt starts, never silently duplicated."""


class InvoiceRequestNotFoundError(SalesDomainError):
    """POS-18: `mark_invoice_issued`/`mark_invoice_error` referenced an
    invoice request id that doesn't exist on this Sale."""


class InvoiceTransitionNotAllowedError(SalesDomainError):
    """POS-18: only a REQUESTED invoice can transition to ISSUED/ERROR —
    an already-resolved request is immutable history."""
