"""Backend authorization, scope validation, and hot-authorization orchestration."""
from __future__ import annotations

from typing import Protocol

from backend.domain.transfers.exceptions import PermissionDeniedError
from backend.domain.transfers.value_objects.authorization_grant import TransferAuthorizationGrant
from .permissions import ALL_TRANSFER_PERMISSIONS


class TransferPermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllTransferPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — it exists so isolated tests can build a policy with an
    explicit, honest permissive checker instead of relying on a fail-open
    None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class TransferScopeChecker(Protocol):
    def can_access_transfer_scope(self, *, user_id: str, branch_id: str | None,
                                  warehouse_id: str | None, location_id: str | None) -> bool: ...


class TransferAuditSink(Protocol):
    def record_hot_authorization(self, grant: TransferAuthorizationGrant) -> None: ...


class TransferAuthorizationPolicy:
    def __init__(self, permissions: TransferPermissionChecker | None = None,
                 scopes: TransferScopeChecker | None = None,
                 audit_sink: TransferAuditSink | None = None) -> None:
        self._permissions = permissions
        self._scopes = scopes
        self._audit_sink = audit_sink

    def require(self, *, user_id: str, permission_code: str,
                branch_id: str | None = None, warehouse_id: str | None = None,
                location_id: str | None = None) -> None:
        if permission_code not in ALL_TRANSFER_PERMISSIONS:
            raise PermissionDeniedError(f"Permiso de transferencias desconocido: {permission_code}")
        if not user_id:
            raise PermissionDeniedError("Operación de transferencias sin usuario autenticado")
        if self._permissions is not None and not self._permissions.has_permission(user_id, permission_code):
            raise PermissionDeniedError(f"El usuario no tiene el permiso {permission_code}")
        if self._scopes is not None and not self._scopes.can_access_transfer_scope(
                user_id=user_id, branch_id=branch_id, warehouse_id=warehouse_id, location_id=location_id):
            raise PermissionDeniedError("El usuario no tiene alcance para el origen o destino de la transferencia")

    def authorize_exception(self, *, requested_by: str, authorized_by: str,
                            permission_code: str, reason: str, operation_id: str,
                            transfer_id: str, shipment_id: str | None = None,
                            receipt_id: str | None = None, quantity=None, weight=None,
                            device_id: str | None = None) -> TransferAuthorizationGrant:
        grant = TransferAuthorizationGrant(
            requested_by=requested_by, authorized_by=authorized_by,
            permission_code=permission_code, reason=reason, operation_id=operation_id,
            transfer_id=transfer_id, shipment_id=shipment_id, receipt_id=receipt_id,
            quantity=quantity, weight=weight, device_id=device_id)
        self.require(user_id=authorized_by, permission_code=permission_code)
        if self._audit_sink is not None:
            self._audit_sink.record_hot_authorization(grant)
        return grant
