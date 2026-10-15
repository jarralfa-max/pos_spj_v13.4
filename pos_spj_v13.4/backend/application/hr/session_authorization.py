"""Verificador de permisos de RR. HH. sobre la sesión viva (HR-01/HR-02).

Concede sólo si la sesión está activa, pertenece al usuario que pide y tiene el
código exacto (``session.tiene_permiso``). La sesión es la viva del shell: un
cambio de sucursal, un cierre de sesión o un refresco de permisos se observan
en cada llamada. Sin sesión, inactiva u otro usuario → niega.
"""

from __future__ import annotations

from backend.domain.hr.policies.authorization_policy import HRPermission


def session_branch_id(session) -> str:
    """Sucursal activa de la sesión. El adaptador vivo expone
    ``active_branch_id``/``sucursal_id`` — NO ``branch_id``: el presentador de
    RR. HH. leía ``branch_id`` y en producción siempre obtenía nada."""
    for attribute in ("active_branch_id", "sucursal_id", "branch_id"):
        value = str(getattr(session, attribute, "") or "").strip()
        if value:
            return value
    return ""


class HRSessionPermissionChecker:
    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))

    def can_access_branch(self, user_id: str, branch_id: str) -> bool:
        """La sucursal activa siempre; las asignadas con
        ``RRHH.ver.sucursales_asignadas``; cualquiera — y una corrida de todas
        las sucursales (``branch_id`` vacío) — con ``RRHH.ver.todas_sucursales``."""
        if not self.has_permission(user_id, HRPermission.VIEW):
            return False
        if self.has_permission(user_id, HRPermission.VIEW_ALL_BRANCHES):
            return True
        requested = str(branch_id or "").strip()
        if not requested:
            return False
        if requested == session_branch_id(self._session):
            return True
        assigned = {str(b) for b in (getattr(self._session, "assigned_branch_ids", None) or ())}
        return requested in assigned and self.has_permission(
            user_id, HRPermission.VIEW_ASSIGNED_BRANCHES)


class AllowAllHRPermissionCheckerForTests:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllHRPermissionCheckerForTests:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False
