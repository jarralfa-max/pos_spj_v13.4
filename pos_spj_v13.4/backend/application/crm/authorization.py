"""CRMAuthorizationPolicy — permission gate for CRM (Leads/Opportunities/
Activities/Cases) operations. Mirrors
backend/application/customers/authorization.py. Fail closed: an
unconfigured policy (no PermissionChecker) never allows.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.crm.permissions import ALL_CRM_PERMISSIONS
from backend.domain.crm.exceptions import CRMConfigurationError, CRMPermissionDeniedError


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllCRMPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllCRMPermissionCheckerForTests:
    """Test-only checker that denies every permission (fail-closed tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class CRMAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "CRMAuthorizationPolicy":
        return cls(AllowAllCRMPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_CRM_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_CRM_PERMISSIONS:
            raise CRMPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise CRMConfigurationError(
                "CRMAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise CRMPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise CRMPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")
