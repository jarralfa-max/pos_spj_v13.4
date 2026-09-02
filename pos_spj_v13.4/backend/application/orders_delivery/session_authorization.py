"""Canonical Pedidos/Delivery RBAC adapter over the live application
session.

Mirrors ``backend/application/loyalty/session_authorization.py``'s
``LoyaltySessionPermissionChecker`` exactly. This is the **real**
``PermissionChecker`` the composition root (`core/app_container.py`) wires
into ``OrdersDeliveryAuthorizationPolicy`` (never a mock).

Identity is validated against the live session, so branch changes, logout
and permission refreshes are observed on every check. A missing session, an
inactive session, a mismatched user, or a session without an active branch
denies (fail closed).
"""

from __future__ import annotations


class OrdersDeliverySessionPermissionChecker:
    """`PermissionChecker` over the live session for
    `OrdersDeliveryAuthorizationPolicy`.

    Grants only when the session is active, belongs to the requesting user,
    has an active branch, and directly holds the canonical `DELIVERY.accion`
    code (``session.tiene_permiso``). No session / inactive session / user
    mismatch / no active branch / no ``tiene_permiso`` → deny.
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
