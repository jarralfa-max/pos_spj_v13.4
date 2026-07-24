"""Domain exceptions for the pricing / costing bounded context.

PRC-1 defines the security-related errors (permission, hot authorization,
segregation of duties, scope). Later phases add operational errors
(InvalidMoneyError, PriceBelowMinimumError, PriceListNotFoundError, …).
"""

from __future__ import annotations


class PricingDomainError(Exception):
    """Base for pricing/costing rule violations."""


class PricingPermissionDeniedError(PricingDomainError):
    """The user lacks the granular permission the action requires."""


class PricingAuthorizationRequiredError(PricingDomainError):
    """Not an outright denial — the operation needs a hot authorization."""


class SegregationOfDutiesError(PricingDomainError):
    """The same user cannot hold two conflicting roles in one operation.

    Whoever creates/edits a price list or a price change may not be the one who
    approves it when the policy demands a second pair of eyes.
    """


class BranchScopeError(PricingDomainError):
    """The user may not set prices for the requested branch."""


class InvalidAuthorizationError(PricingDomainError):
    """A hot authorization or audit entry was built with invalid/missing data."""
