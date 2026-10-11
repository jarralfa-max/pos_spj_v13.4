"""QuotesAuthorizationPolicy — mismo contrato que la del CRM: falla cerrada."""

from __future__ import annotations

from backend.application.quotes.permissions import ALL_QUOTE_PERMISSIONS
from backend.domain.quotes.exceptions import QuotePermissionDeniedError, QuotesConfigurationError


class QuotesAuthorizationPolicy:
    def __init__(self, checker=None) -> None:
        self._checker = checker

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        if self._checker is None or not user_id or permission_code not in ALL_QUOTE_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_QUOTE_PERMISSIONS:
            raise QuotePermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise QuotesConfigurationError("QuotesAuthorizationPolicy requiere un PermissionChecker")
        if not user_id:
            raise QuotePermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise QuotePermissionDeniedError(
                f"No tienes permiso para esta acción ({permission_code}).")

    def require_any(self, user_id: str, *codes: str) -> None:
        if any(self.has_permission(user_id, code) for code in codes):
            return
        self.require(user_id, codes[0])
