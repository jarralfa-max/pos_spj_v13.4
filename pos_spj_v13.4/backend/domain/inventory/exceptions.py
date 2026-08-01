"""Domain exceptions for the inventory bounded context.

INV-1 defines the security-related errors (permission, limit, hot authorization,
segregation of duties, scope). Later phases add operational errors
(InsufficientInventoryError, LotExpiredError, TransferAlreadyReceivedError, …).
"""

from __future__ import annotations


class InventoryDomainError(Exception):
    """Base for inventory rule violations."""


class InventoryPermissionDeniedError(InventoryDomainError):
    """The user lacks the granular permission the action requires."""


class InventoryConfigurationError(InventoryDomainError):
    """A security-sensitive component was built without its mandatory wiring
    (e.g. an authorization policy with no PermissionChecker). Fail closed: never
    allow an operation to proceed on an unconfigured authorization gate (§5.1)."""


class InventoryAuthenticationRequiredError(InventoryDomainError):
    """No authenticated session — the operation cannot resolve an actor (§5.4)."""

    code = "AUTHENTICATION_REQUIRED"


class BranchConfigurationRequiredError(InventoryDomainError):
    """The session has no active branch — no fabricated fallback is allowed (§5.4)."""

    code = "BRANCH_CONFIGURATION_REQUIRED"


class WarehouseConfigurationRequiredError(InventoryDomainError):
    """No warehouse is configured/authorized for the operation (§5.4)."""

    code = "WAREHOUSE_CONFIGURATION_REQUIRED"


class InventoryConcurrencyError(InventoryDomainError):
    """An optimistic-locking conflict: the balance row changed underneath us
    (its stored version no longer matches the expected one). The caller must
    re-read and retry — never overwrite blindly (§6.2)."""

    code = "INVENTORY_CONCURRENCY_CONFLICT"


class InventoryLimitExceededError(InventoryDomainError):
    """A quantity/weight/variance limit was exceeded beyond any override."""


class InventoryAuthorizationRequiredError(InventoryDomainError):
    """Not an outright denial — the operation needs a hot authorization."""


class SegregationOfDutiesError(InventoryDomainError):
    """The same user cannot hold two conflicting roles in one operation."""


class BranchScopeError(InventoryDomainError):
    """The user may not operate on the requested branch."""


class WarehouseScopeError(InventoryDomainError):
    """The user may not operate on the requested warehouse/location."""


class InvalidInventoryLimitError(InventoryDomainError):
    """A limit was defined with a float or an otherwise invalid threshold."""


# ── INV-7 lots / expiration ─────────────────────────────────────────────────
class LotNotFoundError(InventoryDomainError):
    pass


class LotRequiredError(InventoryDomainError):
    """The product is lot-controlled but no lot was supplied."""


class LotExpiredError(InventoryDomainError):
    pass


class LotBlockedError(InventoryDomainError):
    """The lot is blocked/quarantined/rejected and cannot be allocated."""


class InsufficientInventoryError(InventoryDomainError):
    """Not enough eligible stock/lots to satisfy the requested quantity."""


# ── INV-8 catch weight ──────────────────────────────────────────────────────
class InvalidCatchWeightError(InventoryDomainError):
    """A weight/pieces capture is malformed or outside the allowed range."""


class ManualWeightAuthorizationRequiredError(InventoryDomainError):
    """A manual weight outside tolerance needs a distinct authorizer (§18, §47)."""
