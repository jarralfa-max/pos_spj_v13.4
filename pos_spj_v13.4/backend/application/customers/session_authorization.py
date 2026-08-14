"""Canonical Customer Master RBAC adapter over the live application session.

The live catalog seeds roles directly with the granular `CLIENTES.accion`
codes (see `core/security/permission_catalog.py` and
`backend/application/customers/permissions.py`) — the same vocabulary used by
`rol_permisos`, the Configuración permission matrix and every other module.
This is the **real** ``PermissionChecker`` the composition root wires into
`CustomerAuthorizationPolicy`/`CRMAuthorizationPolicy` (never a mock).
Mirrors `backend/application/inventory/session_authorization.py`'s
`InventorySessionPermissionChecker` exactly.

Identity is validated against the live session, so branch changes, logout and
permission refreshes are observed on every use-case invocation. A missing
session, an inactive session, a mismatched user, or a session without an
active branch denies (fail closed).
"""

from __future__ import annotations


class CustomerSessionPermissionChecker:
    """`PermissionChecker` over the live session for
    `CustomerAuthorizationPolicy`/`CRMAuthorizationPolicy`.

    Grants only when the session is active, belongs to the requesting user,
    has an active branch, and directly holds the canonical `CLIENTES.accion`/
    `CRM.accion` code (``session.tiene_permiso``). No session / inactive
    session / user mismatch / no active branch / no ``tiene_permiso`` → deny.
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
