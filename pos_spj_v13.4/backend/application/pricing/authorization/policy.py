"""Pricing authorization — permission gate + segregation + scope + hot auth (PRC-1).

Every use case re-validates its permission via an injected RBAC checker; the UI
never carries authorization logic. On top of the gate this policy enforces:
* segregation of duties — whoever created a price list may not approve/activate it
  when the policy demands a second pair of eyes;
* branch scope — a user may only price branches within reach;
* hot authorization — an in-place exception (e.g. selling below the minimum price)
  approved by a distinct user who holds the permission, producing a
  ``PricingAuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.pricing.permissions import (
    ALL_PRICING_PERMISSIONS,
    SEGREGATED_APPROVALS,
)
from backend.domain.pricing.exceptions import (
    BranchScopeError,
    PricingPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.pricing.value_objects.authorization_grant import (
    PricingAuthorizationGrant,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class PricingAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_PRICING_PERMISSIONS:
            raise PricingPermissionDeniedError(
                f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            return  # isolated tests → allow; production always wires a checker
        if not user_id:
            raise PricingPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise PricingPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def has(self, user_id: str, permission_code: str) -> bool:
        """Non-raising check, for read-side gating (hide cost/margin columns)."""
        if permission_code not in ALL_PRICING_PERMISSIONS:
            return False
        if self._checker is None:
            return True
        return bool(user_id) and self._checker.has_permission(user_id, permission_code)

    def ensure_segregation(
        self, *, actor_user_id: str, creator_user_id: str | None, approval_permission: str
    ) -> None:
        if approval_permission not in SEGREGATED_APPROVALS:
            return
        if creator_user_id and actor_user_id and actor_user_id == creator_user_id:
            raise SegregationOfDutiesError(
                "Quien creó la lista de precios no puede aprobarla ni activarla "
                f"({approval_permission}): se requiere un segundo usuario")

    def require_branch(
        self, user_id: str, branch_id: str | None, *,
        allowed_branches: frozenset[str] | set[str] | None,
    ) -> None:
        """``allowed_branches`` None = todas las sucursales (alcance global)."""
        if branch_id is None or allowed_branches is None:
            return
        if branch_id not in allowed_branches:
            raise BranchScopeError(
                f"El usuario {user_id} no puede fijar precios en la sucursal {branch_id}")

    def authorize_exception(
        self, *, authorizer_user_id: str, requested_by: str, permission_code: str,
        operation_id: str, reason: str, entity_id: str | None = None,
        device_id: str | None = None,
    ) -> PricingAuthorizationGrant:
        if not authorizer_user_id:
            raise PricingPermissionDeniedError("La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise SegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return PricingAuthorizationGrant(
            permission_code=permission_code, requested_by=requested_by,
            authorized_by=authorizer_user_id, operation_id=operation_id,
            reason=reason, entity_id=entity_id, device_id=device_id)
