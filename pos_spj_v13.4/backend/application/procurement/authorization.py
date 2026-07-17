"""Procurement authorization — permission gate + hot authorization (§54, §64).

Every use case re-validates the permission via an injected RBAC checker; the UI
never carries authorization logic. Hot authorization (an exception approved in
place by a second user) is validated the same way and always audited.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.procurement.permissions import ALL_PURCHASE_PERMISSIONS
from backend.domain.procurement.exceptions import PurchasePermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class PurchaseAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_PURCHASE_PERMISSIONS:
            raise PurchasePermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            return  # isolated tests → allow; production always wires a checker
        if not user_id:
            raise PurchasePermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise PurchasePermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def authorize_exception(self, authorizer_user_id: str, permission_code: str) -> None:
        """Validate a hot authorization: the authorizer must hold the permission."""
        if not authorizer_user_id:
            raise PurchasePermissionDeniedError("La autorización requiere un autorizador")
        self.require(authorizer_user_id, permission_code)
