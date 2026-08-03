"""Backend-owned permission, limit and hot-authorization policy for Losses."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import ALL_LOSS_PERMISSIONS, LossPermissions
from backend.domain.losses.exceptions import (
    LossConfigurationError,
    LossLimitExceededError,
    LossPermissionDeniedError,
    LossSegregationOfDutiesError,
)
from backend.domain.losses.value_objects.authorization_grant import LossAuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


def _decimal(value, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name} debe usar Decimal, nunca float")
    return value if isinstance(value, Decimal) else Decimal(str(value))


class LossAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return bool(
            self._checker is not None
            and user_id
            and permission_code in ALL_LOSS_PERMISSIONS
            and self._checker.has_permission(user_id, permission_code)
        )

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_LOSS_PERMISSIONS:
            raise LossPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            raise LossConfigurationError(
                "LossAuthorizationPolicy requiere un PermissionChecker")
        if not user_id or not self._checker.has_permission(user_id, permission_code):
            raise LossPermissionDeniedError(
                f"El usuario {user_id or '<vacío>'} no tiene el permiso {permission_code}")

    def authorize_value(
        self,
        *,
        context: LossExecutionContext,
        permission_code: str,
        operation_id: str,
        value_reference,
        approval_limit,
        reason: str,
        target_branch_id: str | None = None,
        target_warehouse_id: str | None = None,
        authorizer_user_id: str | None = None,
    ) -> LossAuthorizationGrant | None:
        """Authorize a loss and return an audit grant only when over limit."""
        self.require(context.actor_user_id, permission_code)
        branch_id = str(target_branch_id or context.active_branch_id)
        context.enforce_branch(branch_id)
        if target_warehouse_id is not None:
            context.enforce_warehouse(target_warehouse_id)

        value = _decimal(value_reference, field_name="value_reference")
        limit = _decimal(approval_limit, field_name="approval_limit")
        if value <= limit:
            return None
        if not authorizer_user_id:
            raise LossLimitExceededError(
                "La pérdida supera el límite y requiere autorización")
        if authorizer_user_id == context.actor_user_id:
            raise LossSegregationOfDutiesError(
                "El autorizador debe ser distinto del solicitante")
        self.require(authorizer_user_id, LossPermissions.APPROVE_OVER_LIMIT)
        return LossAuthorizationGrant(
            permission_code=LossPermissions.APPROVE_OVER_LIMIT,
            requested_by=context.actor_user_id,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            value_reference=value,
            approval_limit=limit,
            branch_id=branch_id,
            warehouse_id=target_warehouse_id,
            device_id=context.device_id,
        )
