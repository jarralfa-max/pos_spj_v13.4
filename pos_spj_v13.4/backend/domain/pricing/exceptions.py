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


class UnknownPriceListStatusError(InvalidPriceListError):
    """The stored status of a price list is not one of the canonical values.

    Carries the RAW stored value so the screen can say exactly what is wrong
    instead of silently treating the list as some other state.
    """

    def __init__(self, raw_status, *, list_id: str | None = None,
                 code: str | None = None) -> None:
        self.raw_status = raw_status
        self.list_id = list_id
        self.code = code
        quien = f"La lista «{code}»" if code else "La lista de precios"
        super().__init__(
            f"{quien} tiene un estado guardado no reconocido: {raw_status!r}. "
            "Los estados válidos son DRAFT, UNDER_REVIEW, APPROVED, ACTIVE e "
            "INACTIVE; no se opera sobre ella hasta corregir el dato.")


class InvalidCostError(PricingDomainError):
    """A product cost is malformed (float, negative)."""


class InvalidMarginPolicyError(PricingDomainError):
    """A margin policy has an invalid minimum price or target margin."""
