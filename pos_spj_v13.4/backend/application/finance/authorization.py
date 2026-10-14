"""FinanceAuthorizationPolicy y su verificador sobre la sesión viva (F02).

Mismo contrato que las de Cotizaciones/CRM: falla cerrada. Sin verificador,
sin usuario, con un código desconocido o sin el permiso → se rechaza y no se
toca ningún registro.
"""

from __future__ import annotations

from backend.application.finance.permissions import ALL_FINANCE_PERMISSIONS
from backend.domain.finance.exceptions import (
    FinanceConfigurationError,
    FinancePermissionDeniedError,
)


class FinanceAuthorizationPolicy:
    def __init__(self, checker=None) -> None:
        self._checker = checker

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        if self._checker is None or not user_id or permission_code not in ALL_FINANCE_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_FINANCE_PERMISSIONS:
            raise FinancePermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise FinanceConfigurationError(
                "FinanceAuthorizationPolicy requiere un PermissionChecker")
        if not user_id or not str(user_id).strip():
            raise FinancePermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(str(user_id), permission_code):
            raise FinancePermissionDeniedError(
                f"No tienes permiso para esta acción ({permission_code}).")


class FinanceSessionPermissionChecker:
    """``PermissionChecker`` sobre la sesión viva: concede sólo si la sesión
    está activa, pertenece al usuario que pide y tiene el código exacto
    (``session.tiene_permiso``). Sin sesión, inactiva, otro usuario → niega."""

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))


class AllowAllFinancePermissionCheckerForTests:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllFinancePermissionCheckerForTests:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False
