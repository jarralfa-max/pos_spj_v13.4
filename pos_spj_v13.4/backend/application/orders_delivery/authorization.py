"""Pedidos/Delivery authorization — permission gate + hot authorization
(master prompt §62, §64, §65). Mirrors
``backend/application/loyalty/authorization.py`` exactly.

Every future use case re-validates its permission via an injected RBAC
checker; nothing in the UI carries authorization logic. Hot authorization
(an approval granted by a second user who holds the permission) always
requires the authorizer to be a distinct user from the requester — master
prompt §64: "quien asigna repartidor no debe liquidar efectivo", "quien
revierte una entrega requiere autorización independiente" — and always
produces an ``AuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.orders_delivery.permissions import ALL_ORDERS_DELIVERY_PERMISSIONS
from backend.domain.orders_delivery.exceptions import (
    OrdersDeliveryConfigurationError,
    OrdersDeliveryPermissionDeniedError,
    OrdersDeliverySegregationOfDutiesError,
)
from backend.domain.orders_delivery.value_objects.authorization_grant import AuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllOrdersDeliveryPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — it exists so isolated tests can build a policy with an
    explicit, honest permissive checker instead of relying on a fail-open
    None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllOrdersDeliveryPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed
    tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class OrdersDeliveryAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "OrdersDeliveryAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security
        paths. Production use cases must be wired with a real
        PermissionChecker; this replaces a fail-open
        ``OrdersDeliveryAuthorizationPolicy()`` default so the null-checker
        path fails closed."""
        return cls(AllowAllOrdersDeliveryPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating — e.g. enabling/disabling a button).
        Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_ORDERS_DELIVERY_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_ORDERS_DELIVERY_PERMISSIONS:
            raise OrdersDeliveryPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed: an unconfigured authorization gate must never
            # allow. Production wires a real checker; tests build one
            # explicitly via permissive_for_tests()/AllowAll.../DenyAll....
            raise OrdersDeliveryConfigurationError(
                "OrdersDeliveryAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas")
        if not user_id:
            raise OrdersDeliveryPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise OrdersDeliveryPermissionDeniedError(
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
        quantity=None,
        weight=None,
        order_id: str | None = None,
        delivery_job_id: str | None = None,
        entity_id: str | None = None,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization/approval and return its audit
        record.

        The authorizer must hold the permission and must be a distinct user
        from the requester — a second pair of eyes (§64/§65). Applies to:
        peso fuera de tolerancia, sustitución excepcional, cancelación
        después de preparación, entrega sin evidencia, cobro incompleto,
        diferencia de liquidación, reverso de entrega entregada, reembolso.
        """
        if not authorizer_user_id:
            raise OrdersDeliveryPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise OrdersDeliverySegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            amount=amount,
            quantity=quantity,
            weight=weight,
            order_id=order_id,
            delivery_job_id=delivery_job_id,
            entity_id=entity_id,
            device_id=device_id,
        )
