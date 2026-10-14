"""Canonical procurement RBAC adapter for the live application session."""

from __future__ import annotations


class ProcurementSessionPermissionChecker:
    """Validate both actor identity and permission against ``container.session``.

    The session remains live, so branch changes, logout and permission refreshes
    are observed by every use case invocation. Missing/inactive sessions deny.
    """

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        branch_id = str(getattr(session, "active_branch_id", "") or "").strip()
        if not branch_id:
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))

    def can_access_branch(self, user_id: str, branch_id: str) -> bool:
        """Auditoría Compras C18: el comando opera sobre la sucursal del
        DOCUMENTO. La sucursal activa siempre; las asignadas con
        ``COMPRAS.ver.sucursales_asignadas``; cualquiera con
        ``COMPRAS.ver.todas_sucursales`` (compra centralizada)."""
        from backend.application.procurement.permissions import PurchasePermissions

        session = self._session
        requested = str(branch_id or "").strip()
        if not requested or not self.has_permission(user_id, PurchasePermissions.VIEW):
            return False
        check = getattr(session, "tiene_permiso", None)
        if check(PurchasePermissions.VIEW_ALL_BRANCHES):
            return True
        if requested == str(getattr(session, "active_branch_id", "") or "").strip():
            return True
        assigned = {str(b) for b in (getattr(session, "assigned_branch_ids", None) or ())}
        return requested in assigned and bool(
            check(PurchasePermissions.VIEW_ASSIGNED_BRANCHES))
