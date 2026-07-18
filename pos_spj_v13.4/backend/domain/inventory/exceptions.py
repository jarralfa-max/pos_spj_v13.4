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
