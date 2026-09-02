"""Fidelidad/Loyalty authorization — permission gate + hot authorization
(master prompt §59, §60, §62). Mirrors
``backend/application/sales/authorization.py`` exactly.

Every future use case re-validates its permission via an injected RBAC
checker; nothing in the UI carries authorization logic. Hot authorization
(an approval granted by a second user who holds the permission) always
requires the authorizer to be a distinct user from the requester — master
prompt §60: "quien ajusta puntos no aprueba su propio ajuste", "quien crea
campaña no la activa solo" — and always produces an ``AuthorizationGrant``
audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.loyalty.permissions import ALL_LOYALTY_PERMISSIONS
from backend.domain.loyalty.exceptions import (
    LoyaltyConfigurationError,
    LoyaltyPermissionDeniedError,
    LoyaltySegregationOfDutiesError,
)
from backend.domain.loyalty.value_objects.authorization_grant import AuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllLoyaltyPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — it exists so isolated tests can build a policy with an
    explicit, honest permissive checker instead of relying on a fail-open
    None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllLoyaltyPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed
    tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class LoyaltyAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "LoyaltyAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security
        paths. Production use cases must be wired with a real
        PermissionChecker; this replaces a fail-open
        ``LoyaltyAuthorizationPolicy()`` default so the null-checker path
        fails closed."""
        return cls(AllowAllLoyaltyPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating — e.g. enabling/disabling a button).
        Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_LOYALTY_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_LOYALTY_PERMISSIONS:
            raise LoyaltyPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed: an unconfigured authorization gate must never
            # allow. Production wires a real checker; tests build one
            # explicitly via permissive_for_tests()/AllowAll.../DenyAll....
            raise LoyaltyConfigurationError(
                "LoyaltyAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise LoyaltyPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise LoyaltyPermissionDeniedError(
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
        entity_id: str | None = None,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization/approval and return its audit
        record.

        The authorizer must hold the permission and must be a distinct user
        from the requester — a second pair of eyes (§60). Applies to:
        ajuste de puntos, activación de campaña, override de cupón,
        aprobación de plantilla/lote (well, that's Loyalty Cards' own
        policy), activación de programa, aprobación de recompensa especial.
        """
        if not authorizer_user_id:
            raise LoyaltyPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise LoyaltySegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            amount=amount,
            entity_id=entity_id,
            device_id=device_id,
        )
