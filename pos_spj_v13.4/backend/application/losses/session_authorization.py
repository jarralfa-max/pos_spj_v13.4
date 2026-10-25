"""Fail-closed adapter between the live desktop session and Losses RBAC.

Auditoría de permisos 968e0bc (PER-04): con los códigos planos (`LOSSES_*`) este
verificador preguntaba a la sesión por códigos que ningún rol podía tener, así
que Mermas sólo existía para los roles de acceso total. Ahora los códigos son
`MERMA.<accion>`, otorgables desde Configuración, y se consultan tal cual.

Respaldo grueso, el mismo criterio que fijó la reauditoría de Productos
(PROD-22): `MERMA.ver` —sembrado a gerente, almacén y sólo lectura— concede las
PÁGINAS DE CONSULTA del módulo, nada más. Ninguna mutación, ni el costo, ni la
auditoría, ni la configuración, ni el alcance a otras sucursales: esos sólo con
su código granular.
"""

from backend.application.losses.permissions import LossPermissions as P

#: Lecturas de página que concede `MERMA.ver` (= `LossPermissions.VIEW`).
VIEW_GRANTS_PAGES = frozenset({
    P.ACCESS, P.OVERVIEW_VIEW, P.REGISTRATION_VIEW, P.PENDING_VIEW, P.PRODUCTION_VIEW,
    P.INVENTORY_VIEW, P.EXPIRY_DAMAGE_VIEW, P.QUALITY_VIEW, P.YIELD_VIEW, P.RECOVERY_VIEW,
    P.DISPOSITION_VIEW, P.INVESTIGATION_VIEW, P.CORRECTIVE_ACTION_VIEW, P.ALERT_VIEW,
    P.ANALYTICS_VIEW,
})


class LossSessionPermissionChecker:
    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not bool(getattr(session, "is_active", False)):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        if not str(getattr(session, "active_branch_id", "") or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        if not callable(check):
            return False
        if check(permission_code):
            return True
        return permission_code in VIEW_GRANTS_PAGES and bool(check(P.VIEW))
