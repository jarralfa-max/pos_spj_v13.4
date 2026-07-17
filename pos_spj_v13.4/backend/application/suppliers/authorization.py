"""Supplier authorization policy — permission gate for supplier operations.

Never authorizes by hardcoded role; it consults an injected permission checker
(the central RBAC). With no checker wired (isolated tests) it allows, so the
domain rules stay the unit under test. Production always wires a checker.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.suppliers.permissions import ALL_SUPPLIER_PERMISSIONS
from backend.domain.suppliers.exceptions import PermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class SupplierAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_SUPPLIER_PERMISSIONS:
            raise PermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            return
        if not user_id:
            raise PermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise PermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")
