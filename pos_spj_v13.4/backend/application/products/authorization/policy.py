"""Products authorization — permission gate + segregation + scope + hot auth (§37-39, §48).

Every use case re-validates its permission via an injected RBAC checker; the UI
never carries authorization logic. On top of the permission gate this policy
enforces:

* segregation of duties (§39) — whoever created a recipe/yield/import/product may
  not be the one who approves or activates it when the policy demands a second
  pair of eyes;
* scope (§37) — a user may only operate on branches within reach, and internal /
  meat / cost-reference products require their own view permission;
* hot authorization (§48) — an in-place exception approved by a distinct user who
  holds the permission, always producing a ``ProductAuthorizationGrant`` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.products.permissions import (
    ALL_PRODUCT_PERMISSIONS,
    SEGREGATED_APPROVALS,
    ProductPermissions,
)
from backend.domain.products.exceptions import (
    BranchScopeError,
    ProductPermissionDeniedError,
    ProductTypeScopeError,
    SegregationOfDutiesError,
)
from backend.domain.products.value_objects.authorization_grant import (
    ProductAuthorizationGrant,
)


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class ProductsAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    # ── permiso ───────────────────────────────────────────────────────────
    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_PRODUCT_PERMISSIONS:
            raise ProductPermissionDeniedError(
                f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            return  # isolated tests → allow; production always wires a checker
        if not user_id:
            raise ProductPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise ProductPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}")

    def has(self, user_id: str, permission_code: str) -> bool:
        """Non-raising check, for read-side gating (hide internal/cost columns)."""
        if permission_code not in ALL_PRODUCT_PERMISSIONS:
            return False
        if self._checker is None:
            return True
        return bool(user_id) and self._checker.has_permission(user_id, permission_code)

    # ── segregación de funciones (§39) ────────────────────────────────────
    def ensure_segregation(
        self,
        *,
        actor_user_id: str,
        creator_user_id: str | None,
        approval_permission: str,
    ) -> None:
        """A create→approve/activate pair may not be closed by the same user.

        ``approval_permission`` is the permission being exercised now (e.g.
        ``PRODUCTS_RECIPE_APPROVE``); if it maps to a creation permission in
        ``SEGREGATED_APPROVALS`` and the actor is the original creator, the
        operation is blocked regardless of RBAC.
        """
        if approval_permission not in SEGREGATED_APPROVALS:
            return
        if creator_user_id and actor_user_id and actor_user_id == creator_user_id:
            raise SegregationOfDutiesError(
                "Quien creó el registro no puede aprobarlo ni activarlo "
                f"({approval_permission}): se requiere un segundo usuario")

    # ── alcance (§37) ─────────────────────────────────────────────────────
    def require_branch(
        self,
        user_id: str,
        branch_id: str | None,
        *,
        allowed_branches: frozenset[str] | set[str] | None,
    ) -> None:
        """``allowed_branches`` None = todas las sucursales (alcance global)."""
        if branch_id is None or allowed_branches is None:
            return
        if branch_id not in allowed_branches:
            raise BranchScopeError(
                f"El usuario {user_id} no puede operar en la sucursal {branch_id}")

    def require_product_type_visibility(
        self,
        user_id: str,
        *,
        internal_only: bool = False,
        is_meat: bool = False,
    ) -> None:
        """Internos y cárnicos sólo son visibles con su permiso específico (§33)."""
        if internal_only:
            self.require(user_id, ProductPermissions.VIEW_INTERNAL)
        if is_meat:
            self.require(user_id, ProductPermissions.VIEW_MEAT)

    # ── autorización en caliente (§48) ────────────────────────────────────
    def authorize_exception(
        self,
        *,
        authorizer_user_id: str,
        requested_by: str,
        permission_code: str,
        operation_id: str,
        reason: str,
        entity_id: str | None = None,
        device_id: str | None = None,
    ) -> ProductAuthorizationGrant:
        """Validate a hot authorization and return its audit record.

        The authorizer must hold the permission and be a distinct user from the
        requester (a hot authorization is a second pair of eyes).
        """
        if not authorizer_user_id:
            raise ProductPermissionDeniedError(
                "La autorización requiere un autorizador")
        if authorizer_user_id == requested_by:
            raise SegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante")
        self.require(authorizer_user_id, permission_code)
        return ProductAuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            entity_id=entity_id,
            device_id=device_id,
        )
