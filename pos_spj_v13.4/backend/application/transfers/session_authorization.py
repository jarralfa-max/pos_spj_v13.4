"""Transfers RBAC adapter over the live application session.

Unlike Inventory (whose ``InventoryPermissions.*`` vocabulary IS the catalog
vocabulary — see ``backend/application/inventory/session_authorization.py``),
the granular ``TransferPermissions.*`` codes used by
``TransferAuthorizationPolicy`` (e.g. ``TRANSFERS_REQUEST_CREATE``) do not
match what is actually registered in
``core/security/permission_catalog.py``, which only exposes a coarse
``"TRANSFERENCIAS": ["ver", "crear", "recibir", "cancelar"]``. This checker
translates the handful of codes needed by the use cases wired so far; every
other ``TransferPermissions.*`` code has no catalog counterpart yet and denies
fail-closed. Widen ``_PERMISSION_MAP`` as later phases wire more use cases —
do not invent new catalog actions here without also registering them in
``permission_catalog.py``.
"""

from __future__ import annotations

# TransferPermissions.* code -> registered "TRANSFERENCIAS.accion" catalog code.
_PERMISSION_MAP = {
    "TRANSFERS_ACCESS": "TRANSFERENCIAS.ver",
    "TRANSFERS_REQUEST_VIEW": "TRANSFERENCIAS.ver",
    "TRANSFERS_REQUEST_CREATE": "TRANSFERENCIAS.crear",
}


class TransferSessionPermissionChecker:
    """``TransferPermissionChecker`` over the live session for
    ``TransferAuthorizationPolicy``.

    Grants only when the session is active, belongs to the requesting user,
    has an active branch, and the mapped catalog code is held
    (``session.tiene_permiso``). No session / inactive session / user mismatch
    / no active branch / unmapped permission code / no ``tiene_permiso`` →
    deny.
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
        catalog_code = _PERMISSION_MAP.get(permission_code)
        if catalog_code is None:
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(catalog_code))
