"""Products authorization (PROD-1): permission gate, segregation, scope, hot auth."""

from backend.application.products.authorization.policy import (
    PermissionChecker,
    ProductsAuthorizationPolicy,
)

__all__ = ["PermissionChecker", "ProductsAuthorizationPolicy"]
