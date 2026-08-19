"""Sales/POS authorization — permission gate + hot authorization (§26, §61,
§62). Mirrors backend/application/inventory/authorization.py exactly.

Every use case re-validates its permission via an injected RBAC checker; the
UI never carries authorization logic — this replaces the hardcoded
``{"admin", "gerente"}`` role-name check that used to gate the Devolución
button (master prompt §61: "No autorizar por nombre de rol").

Hot authorization (an exception approved in place by a second user who holds
the permission) always requires the authorizer to be a distinct user from the
requester — master prompt §62: "cajero no autoriza su propio descuento
protegido" — and always produces an ``AuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.sales.permissions import ALL_SALES_PERMISSIONS
from backend.domain.sales.exceptions import (
    SalesConfigurationError,
    SalesPermissionDeniedError,
    SalesSegregationOfDutiesError,
)
from backend.domain.sales.value_objects.authorization_grant import AuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllSalesPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — it exists so isolated tests can build a policy with an
    explicit, honest permissive checker instead of relying on a fail-open
    None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllSalesPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed
    tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class SalesAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "SalesAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security
        paths. Production use cases must be wired with a real
        PermissionChecker; this replaces a fail-open ``SalesAuthorizationPolicy()``
        default so the null-checker path fails closed."""
        return cls(AllowAllSalesPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating — e.g. enabling/disabling a button).
        Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_SALES_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_SALES_PERMISSIONS:
            raise SalesPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed: an unconfigured authorization gate must never
            # allow. Production wires a real checker; tests build one
            # explicitly via permissive_for_tests()/AllowAll.../DenyAll....
            raise SalesConfigurationError(
                "SalesAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise SalesPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise SalesPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def authorize_exception(
        self,
        *,
        authorizer_user_id: str,
        requested_by: str,
        permission_code: str,
        operation_id: str,
        reason: str,
        amount=None,
        sale_id: str | None = None,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization and return its audit record.

        The authorizer must hold the permission and must be a distinct user
        from the requester (a hot authorization is a second pair of eyes —
        §62). Applies to: descuento alto, precio override, venta sin stock,
        cancelación, devolución, reimpresión, crédito especial (§26).
        """
        if not authorizer_user_id:
            raise SalesPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise SalesSegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            amount=amount,
            sale_id=sale_id,
            device_id=device_id,
        )
