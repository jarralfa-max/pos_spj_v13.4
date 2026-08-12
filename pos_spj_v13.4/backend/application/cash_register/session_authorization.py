"""Canonical Caja RBAC adapters over the live application session.

Like Compras, Caja validates the exact ``CAJA.accion`` code held by
``SessionContext.tiene_permiso``. There is no compatibility mapping from old
``CASH_*`` codes and no role-name shortcut.
"""

from __future__ import annotations

from backend.application.cash_register.permissions import CashPermissions


class CashSessionPermissionChecker:
    """Fail-closed PermissionChecker for ``CashAuthorizationPolicy``."""

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


class CashSessionBranchScopeChecker:
    """Branch scope checker backed by the live session and granular CAJA grants."""

    def __init__(self, session) -> None:
        self._session = session

    def can_access_branch(self, *, user_id: str, branch_id: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        requested = str(branch_id or "").strip()
        active = str(getattr(session, "active_branch_id", "") or "").strip()
        check = getattr(session, "tiene_permiso", None)
        if not requested or not active or not callable(check):
            return False
        if check(CashPermissions.VIEW_ALL_BRANCHES):
            return True
        return requested == active and (
            check(CashPermissions.VIEW_OWN_BRANCH)
            or check(CashPermissions.VIEW_ASSIGNED_BRANCHES)
            or check(CashPermissions.ACCESS)
        )
