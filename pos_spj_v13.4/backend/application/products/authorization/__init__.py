"""Products authorization (PROD-1): permission gate, segregation, scope, hot auth."""

from backend.application.products.authorization.policy import (
    AllowAllProductsPermissionCheckerForTests,
    DenyAllProductsPermissionCheckerForTests,
    PermissionChecker,
    ProductsAuthorizationPolicy,
)

__all__ = [
    "AllowAllProductsPermissionCheckerForTests",
    "DenyAllProductsPermissionCheckerForTests",
    "PermissionChecker",
    "ProductsAuthorizationPolicy",
]
