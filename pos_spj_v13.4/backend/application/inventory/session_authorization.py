"""Canonical inventory RBAC adapter over the live application session (P0-A §5.2).

The live catalog seeds roles with Spanish module-level codes (`inventario.ver`,
`inventario.editar`, `inventario.ajustar`, `inventario.transferir`). The canonical
inventory context reasons in granular English codes (`INVENTORY_*`). This adapter
bridges canonical → legacy so the real session grants canonical permissions without
re-seeding roles, and it is the **real** ``PermissionChecker`` production wires into
``InventoryUseCaseFactory`` (never a mock — §23).

Identity is validated against the live session, so branch changes, logout and
permission refreshes are observed on every use-case invocation. A missing session,
a mismatched user, or a session without ``tiene_permiso`` denies (fail closed).
"""

from __future__ import annotations

#: Legacy module code that grants read-only inventory access.
_LEGACY_VIEW = ("inventario.ver",)
#: Legacy module code that grants inventory mutations.
_LEGACY_EDIT = ("inventario.editar",)


def legacy_codes_for(canonical_code: str) -> tuple[str, ...]:
    """Map a canonical ``INVENTORY_*`` permission to the legacy codes that grant it.

    Reads are granted by ``inventario.ver``; adjustments and transfers by their
    specific legacy codes (plus edit); every other mutation by ``inventario.editar``.
    A role already migrated to the English canonical code also works (checked first
    by the caller).
    """
    code = str(canonical_code or "").upper()
    if any(tok in code for tok in ("_VIEW", "_READ", "_EXPORT", "_LIST", "VIEW_")):
        return _LEGACY_VIEW
    if "ADJUST" in code:
        return ("inventario.ajustar", "inventario.editar")
    if "TRANSFER" in code:
        return ("inventario.transferir", "inventario.editar")
    return _LEGACY_EDIT


class InventorySessionPermissionChecker:
    """`PermissionChecker` over the live session for `InventoryAuthorizationPolicy`.

    Grants when the session holds the canonical English code directly or any of the
    mapped legacy codes (``session.tiene_permiso``). Admin/`*` sessions grant all via
    ``tiene_permiso``. No session / no ``tiene_permiso`` / user mismatch → deny.
    """

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None:
            return False
        check = getattr(session, "tiene_permiso", None)
        if not callable(check):
            return False
        session_user_id = str(getattr(session, "user_id", None)
                              or getattr(session, "usuario", None) or "").strip()
        if session_user_id and session_user_id != str(user_id or "").strip():
            return False
        if check(permission_code):  # role already migrated to the canonical code
            return True
        return any(check(code) for code in legacy_codes_for(permission_code))
