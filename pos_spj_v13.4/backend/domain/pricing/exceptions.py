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


# ── PRC-2 dominio de precios/costos ──────────────────────────────────────────
class InvalidMoneyError(PricingDomainError):
    """A Money amount is a float, negative where forbidden, or mismatched currency."""


class CurrencyMismatchError(PricingDomainError):
    """Two Money values of different currencies were combined."""


class PriceBelowMinimumError(PricingDomainError):
    """A sale price is below the product's minimum price (needs override)."""


class InvalidPriceListError(PricingDomainError):
    """A price list / product price / volume tier is malformed."""


class InvalidCostError(PricingDomainError):
    """A product cost is malformed (float, negative)."""


class InvalidMarginPolicyError(PricingDomainError):
    """A margin policy has an invalid minimum price or target margin."""
