"""Supplier authorization policy — permission gate for supplier operations.

Never authorizes by hardcoded role; it consults an injected permission checker
(the central RBAC).

Auditoría de permisos 968e0bc (PER-02): sin verificador PERMITÍA todo («para
pruebas aisladas»), y el caso de uso base caía en esa política si nadie le
cableaba una. Ahora falla cerrada; las pruebas usan `permissive_for_tests()`.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.suppliers.permissions import ALL_SUPPLIER_PERMISSIONS
from backend.domain.suppliers.exceptions import PermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllSupplierPermissionCheckerForTests:
    """Sólo pruebas: concede todo. NUNCA en producción."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class SupplierAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "SupplierAuthorizationPolicy":
        return cls(AllowAllSupplierPermissionCheckerForTests())

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_SUPPLIER_PERMISSIONS:
            raise PermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise PermissionDeniedError(
                "Proveedores sin verificador de permisos: la operación se rechaza")
        if not user_id:
            raise PermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise PermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")
