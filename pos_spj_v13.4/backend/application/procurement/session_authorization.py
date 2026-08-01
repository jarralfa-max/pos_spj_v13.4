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
