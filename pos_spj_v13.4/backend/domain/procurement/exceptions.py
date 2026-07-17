"""Domain exceptions for the procurement bounded context."""

from __future__ import annotations


class ProcurementDomainError(Exception):
    """Base for procurement rule violations."""


class PurchasePermissionDeniedError(ProcurementDomainError):
    pass


class PurchaseLimitExceededError(ProcurementDomainError):
    pass


class AuthorizationRequiredError(ProcurementDomainError):
    """Not an outright denial — the operation needs a hot authorization."""


class SupplierNotEligibleError(ProcurementDomainError):
    pass


class SegregationOfDutiesError(ProcurementDomainError):
    pass


class BranchScopeError(ProcurementDomainError):
    pass


class TimeWindowError(ProcurementDomainError):
    pass


class InvalidMoneyError(ProcurementDomainError):
    pass


class InvalidPaymentSourceError(ProcurementDomainError):
    pass


class InvalidPurchaseStateError(ProcurementDomainError):
    pass
