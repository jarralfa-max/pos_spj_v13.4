"""CustomerAuthorizationPolicy — permission gate for Customer Master
operations (CRM-3, wiring CRM-2's CustomerPermissions for the first time).

Fail closed (mirrors backend/application/inventory/authorization.py, not
Suppliers' fail-open-for-isolated-tests variant): an unconfigured policy
(no PermissionChecker) never allows. Tests build an explicit
``permissive_for_tests()`` policy instead of relying on a null-checker
default — same discipline CRM-2's ``CustomerDataScopeResolver`` already
established (§5.1-equivalent).
"""

from __future__ import annotations

from typing import Protocol

from backend.application.customers.permissions import ALL_CUSTOMER_PERMISSIONS
from backend.domain.customers.exceptions import (
    CustomerConfigurationError,
    CustomerPermissionDeniedError,
)
from backend.domain.customers.value_objects.authorization_grant import (
    CustomerAuthorizationGrant,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllCustomerPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — tests use it to build an explicit, honest permissive
    policy instead of relying on a fail-open null checker."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllCustomerPermissionCheckerForTests:
    """Test-only checker that denies every permission (fail-closed tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class CustomerAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "CustomerAuthorizationPolicy":
        return cls(AllowAllCustomerPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_CUSTOMER_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_CUSTOMER_PERMISSIONS:
            raise CustomerPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise CustomerConfigurationError(
                "CustomerAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise CustomerPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise CustomerPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def authorize_exception(
        self, *, authorizer_user_id: str, requested_by: str, permission_code: str,
        operation_id: str, reason: str, credit_amount=None, device_id: str | None = None,
    ) -> CustomerAuthorizationGrant:
        """Validate a hot authorization (§74) and return its audit record.

        The authorizer must hold the permission and must be a distinct user
        from the requester — enforced twice: here (policy-level, before
        touching the domain) and again inside ``CustomerAuthorizationGrant``
        itself (value-object invariant, CRM-2), so it holds even if a
        caller builds the grant directly.
        """
        if not authorizer_user_id:
            raise CustomerPermissionDeniedError("La autorización requiere un autorizador")
        self.require(authorizer_user_id, permission_code)
        return CustomerAuthorizationGrant(
            permission_code=permission_code, requested_by=requested_by,
            authorized_by=authorizer_user_id, operation_id=operation_id, reason=reason,
            credit_amount=credit_amount, device_id=device_id,
        )
