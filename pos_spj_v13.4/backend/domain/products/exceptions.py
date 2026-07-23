"""Domain exceptions for the products bounded context.

PROD-1 defines the security-related errors (permission, hot authorization,
segregation of duties, scope, duplicate operation). Later phases add the
operational errors from §47 (ProductNotFoundError, InvalidMeatClassificationError,
RecipeCycleDetectedError, YieldProfileInvalidError, …) next to these.
"""

from __future__ import annotations


class ProductsDomainError(Exception):
    """Base for products rule violations."""


class ProductPermissionDeniedError(ProductsDomainError):
    """The user lacks the granular permission the action requires."""


class ProductAuthorizationRequiredError(ProductsDomainError):
    """Not an outright denial — the operation needs a hot authorization."""


class SegregationOfDutiesError(ProductsDomainError):
    """The same user cannot hold two conflicting roles in one operation.

    §39: whoever creates a recipe/yield/import must not approve or activate it
    when the policy demands a second pair of eyes.
    """


class BranchScopeError(ProductsDomainError):
    """The user may not operate on the requested branch."""


class ProductTypeScopeError(ProductsDomainError):
    """The user may not operate on the requested product type.

    Internal / meat / cost-reference views are gated by their own permissions
    (§37-38); a user without them may not read or mutate those products.
    """


class DuplicateOperationError(ProductsDomainError):
    """An operation_id was replayed (idempotency guard)."""


class InvalidAuthorizationError(ProductsDomainError):
    """A hot authorization or audit entry was built with invalid/missing data."""


# ── PROD-2 Product Master ────────────────────────────────────────────────────
class ProductNotFoundError(ProductsDomainError):
    """No product exists for the given id/code."""


class ProductAlreadyExistsError(ProductsDomainError):
    """A product with the same code/barcode already exists."""


class InvalidProductTypeError(ProductsDomainError):
    """An unknown or inconsistent product type was supplied."""


class InvalidProductStateError(ProductsDomainError):
    """A lifecycle transition is not allowed from the current state."""


class ProductInactiveError(ProductsDomainError):
    """The product is not ACTIVE and cannot be used for the requested operation."""


class ProductDiscontinuedError(ProductsDomainError):
    """The product is DISCONTINUED/ARCHIVED and cannot be reactivated in place."""


class ProductIncompleteError(ProductsDomainError):
    """The product cannot be activated while required master data is missing (§7)."""


class SpeciesRequiredError(ProductsDomainError):
    """A meat product type was created without a species (§7, §11)."""
