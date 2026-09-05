"""Assets/EAM authorization — permission gate + hot authorization (§71-85).

Every use case re-validates its permission via an injected RBAC checker; the
UI never carries authorization logic. Hot authorization (an exception approved
in place by a second user) always requires a distinct authorizer (§84
segregation of duties: whoever requests a disposal/transfer/capitalization
cannot approve their own request) and is always audited.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.assets.permissions import ALL_ASSET_PERMISSIONS
from backend.domain.assets.exceptions import (
    AssetPermissionDeniedError,
    SegregationOfDutiesError,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllAssetPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — isolated tests build a policy with an explicit, honest
    permissive checker instead of relying on a fail-open None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllAssetPermissionCheckerForTests:
    """Test-only checker that denies every permission (fail-closed tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class AssetAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "AssetAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security paths.
        Production use cases must be wired with a real PermissionChecker."""
        return cls(AllowAllAssetPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_ASSET_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_ASSET_PERMISSIONS:
            raise AssetPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed: an unconfigured authorization gate must never allow.
            raise AssetPermissionDeniedError(
                "AuthorizationChecker no configurado; autorización denegada")
        if not user_id:
            raise AssetPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise AssetPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def authorize_exception(self, *, authorizer_user_id: str, requested_by: str,
                             permission_code: str) -> None:
        """Validate a hot/two-person authorization (§84-85): the authorizer
        must hold the permission and must be a distinct user from the
        requester — e.g. baja, pérdida/robo, capitalización sensible, override
        de inspección, cierre de work order crítico, reimpresión controlada."""
        if not authorizer_user_id:
            raise AssetPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise SegregationOfDutiesError(
                "El autorizador debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
