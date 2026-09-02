"""Loyalty Cards authorization — permission gate + hot authorization
(master prompt §59, §60). Mirrors
``backend/application/loyalty/authorization.py`` exactly, kept as a
separate policy class because Loyalty Cards is its own bounded context with
its own segregation-of-duties roles (§60: Diseñador de tarjetas, Aprobador
de plantillas, Operador de impresión).

Hot authorization always requires the authorizer to be a distinct user from
the requester — §60: "quien diseña plantilla no la activa solo", "quien
genera lote no lo aprueba solo" — and always produces an
``AuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.loyalty_cards.permissions import ALL_LOYALTY_CARDS_PERMISSIONS
from backend.domain.loyalty_cards.exceptions import (
    LoyaltyCardConfigurationError,
    LoyaltyCardPermissionDeniedError,
    LoyaltyCardSegregationOfDutiesError,
)
from backend.domain.loyalty_cards.value_objects.authorization_grant import AuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllLoyaltyCardsPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllLoyaltyCardsPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed
    tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class LoyaltyCardsAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "LoyaltyCardsAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security
        paths. Production use cases must be wired with a real
        PermissionChecker."""
        return cls(AllowAllLoyaltyCardsPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_LOYALTY_CARDS_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_LOYALTY_CARDS_PERMISSIONS:
            raise LoyaltyCardPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise LoyaltyCardConfigurationError(
                "LoyaltyCardsAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise LoyaltyCardPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise LoyaltyCardPermissionDeniedError(
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
        card_id: str | None = None,
        batch_id: str | None = None,
        template_id: str | None = None,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization/approval (plantilla, lote,
        reimpresión, rotación de QR) and return its audit record."""
        if not authorizer_user_id:
            raise LoyaltyCardPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise LoyaltyCardSegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            amount=amount,
            card_id=card_id,
            batch_id=batch_id,
            template_id=template_id,
            device_id=device_id,
        )
