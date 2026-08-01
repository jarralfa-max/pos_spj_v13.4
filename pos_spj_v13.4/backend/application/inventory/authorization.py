"""Inventory authorization — permission gate + hot authorization (§45, §48).

Every use case re-validates its permission via an injected RBAC checker; the UI
never carries authorization logic. Hot authorization (an exception approved in
place by a second user who holds the permission) is validated the same way and
always produces an ``AuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.inventory.permissions import ALL_INVENTORY_PERMISSIONS
from backend.domain.inventory.exceptions import (
    InventoryConfigurationError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.inventory.value_objects.authorization_grant import (
    AuthorizationGrant,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllInventoryPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in production —
    it exists so isolated tests can build a policy with an explicit, honest
    permissive checker instead of relying on a fail-open None (§5.1)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllInventoryPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class InventoryAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "InventoryAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security paths.
        Production use cases must be wired with a real PermissionChecker; this
        replaces the old fail-open ``InventoryAuthorizationPolicy()`` default so
        the null-checker path can fail closed (§5.1)."""
        return cls(AllowAllInventoryPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_INVENTORY_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_INVENTORY_PERMISSIONS:
            raise InventoryPermissionDeniedError(
                f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed (§5.1): an unconfigured authorization gate must never
            # allow. Production wires a real checker; tests build one explicitly.
            raise InventoryConfigurationError(
                "InventoryAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise InventoryPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise InventoryPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def authorize_exception(
        self,
        *,
        authorizer_user_id: str,
        requested_by: str,
        permission_code: str,
        operation_id: str,
        reason: str,
        quantity=None,
        weight=None,
        value_reference=None,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization and return its audit record.

        The authorizer must hold the permission and must be a distinct user
        from the requester (a hot authorization is a second pair of eyes).
        """
        if not authorizer_user_id:
            raise InventoryPermissionDeniedError(
                "La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise SegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            quantity=quantity,
            weight=weight,
            value_reference=value_reference,
            device_id=device_id,
        )
