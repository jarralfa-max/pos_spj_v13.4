"""Fail-closed permission, branch scope, and hot authorization policy."""
from typing import Protocol

from backend.application.cash_register.permissions import ALL_CASH_PERMISSIONS
from backend.domain.cash_register.exceptions import CashConfigurationError, CashPermissionDeniedError
from backend.domain.cash_register.value_objects.security_artifacts import CashAuthorizationGrant, CashSecurityAuditEntry


class CashPermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class CashBranchScopeChecker(Protocol):
    def can_access_branch(self, *, user_id: str, branch_id: str) -> bool: ...


class CashSecurityAuditSink(Protocol):
    def record_hot_authorization(self, grant: CashAuthorizationGrant) -> None: ...
    def record_security_audit(self, entry: CashSecurityAuditEntry) -> None: ...


class CashAuthorizationPolicy:
    def __init__(self, permissions: CashPermissionChecker | None = None,
                 scopes: CashBranchScopeChecker | None = None,
                 audit_sink: CashSecurityAuditSink | None = None) -> None:
        self._permissions, self._scopes, self._audit = permissions, scopes, audit_sink

    def has_permission(self, *, user_id: str, permission_code: str,
                       branch_id: str | None = None) -> bool:
        try:
            self.require(user_id=user_id, permission_code=permission_code, branch_id=branch_id)
        except (CashConfigurationError, CashPermissionDeniedError):
            return False
        return True

    def require(self, *, user_id: str, permission_code: str,
                branch_id: str | None = None) -> None:
        if permission_code not in ALL_CASH_PERMISSIONS:
            raise CashPermissionDeniedError(f"Permiso de Caja desconocido: {permission_code}")
        if self._permissions is None:
            raise CashConfigurationError("CashAuthorizationPolicy requiere PermissionChecker")
        if not user_id:
            raise CashPermissionDeniedError("Operación de Caja sin usuario autenticado")
        if not self._permissions.has_permission(user_id, permission_code):
            raise CashPermissionDeniedError(f"El usuario no tiene el permiso {permission_code}")
        if branch_id is not None:
            if self._scopes is None:
                raise CashConfigurationError("La operación por sucursal requiere BranchScopeChecker")
            if not self._scopes.can_access_branch(user_id=user_id, branch_id=branch_id):
                raise CashPermissionDeniedError("El usuario no tiene alcance para esta sucursal")

    def authorize_exception(self, *, requested_by: str, authorized_by: str,
                            permission_code: str, reason: str, operation_id: str,
                            entity_id: str, branch_id: str, amount=None,
                            device_id: str | None = None) -> CashAuthorizationGrant:
        self.require(user_id=authorized_by, permission_code=permission_code, branch_id=branch_id)
        grant = CashAuthorizationGrant(
            requested_by=requested_by, authorized_by=authorized_by,
            permission_code=permission_code, reason=reason, operation_id=operation_id,
            entity_id=entity_id, branch_id=branch_id, amount=amount, device_id=device_id)
        if self._audit is None:
            raise CashConfigurationError("La autorización en caliente requiere AuditSink")
        entry = CashSecurityAuditEntry(
            action="CASH_HOT_AUTHORIZATION_GRANTED", actor_user_id=authorized_by,
            entity_id=entity_id, branch_id=branch_id, operation_id=operation_id,
            reason=reason, authorization_id=grant.id, amount=grant.amount, device_id=device_id)
        self._audit.record_hot_authorization(grant)
        self._audit.record_security_audit(entry)
        return grant
