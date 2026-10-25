"""Transfers RBAC adapter over the live application session.

Auditoría de permisos 968e0bc (PER-04). Hasta aquí `TransferPermissions.*` eran
códigos PLANOS (`TRANSFERS_APPROVE`) fuera del catálogo, y este verificador sólo
traducía tres a `TRANSFERENCIAS.ver`/`crear`; todo lo demás devolvía `False`
ANTES de consultar la sesión. Medido: aprobar, rechazar, surtir, despachar y
recibir una transferencia se denegaban a TODOS — administrador y dueño
incluidos —, así que el ciclo que orquesta `TransferCycleService` no podía pasar
de «solicitud enviada».

Ahora los códigos son `TRANSFERENCIAS.<accion>`, registrados en el catálogo y
otorgables desde Configuración, y se consultan tal cual. Respaldo grueso, el
mismo criterio que Productos (PROD-22) y Mermas: `TRANSFERENCIAS.ver` concede las
páginas de consulta, y `TRANSFERENCIAS.crear` la captura de la solicitud — lo
que ya concedía antes. Nada más: aprobar, mover mercancía, diferencias,
reversos, auditoría y configuración sólo con su código granular.
"""

from __future__ import annotations

from backend.application.transfers.permissions import TransferPermissions as P

#: Respaldo grueso: código granular → acción gruesa sembrada que lo concede.
COARSE_FALLBACK = {
    P.ACCESS: "TRANSFERENCIAS.ver",
    P.DASHBOARD_VIEW: "TRANSFERENCIAS.ver",
    P.REQUEST_VIEW: "TRANSFERENCIAS.ver",
    P.DISPATCH_VIEW: "TRANSFERENCIAS.ver",
    P.RECEIVE_VIEW: "TRANSFERENCIAS.ver",
    P.DIFFERENCE_VIEW: "TRANSFERENCIAS.ver",
    P.REQUEST_CREATE: "TRANSFERENCIAS.crear",
}


class TransferSessionPermissionChecker:
    """``TransferPermissionChecker`` over the live session for
    ``TransferAuthorizationPolicy``.

    Grants only when the session is active, belongs to the requesting user,
    has an active branch, and holds the granular code or its coarse fallback
    (``session.tiene_permiso``). No session / inactive session / user mismatch
    / no active branch / no ``tiene_permiso`` → deny.
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
        if not callable(check):
            return False
        if check(permission_code):
            return True
        coarse = COARSE_FALLBACK.get(permission_code)
        return coarse is not None and bool(check(coarse))
