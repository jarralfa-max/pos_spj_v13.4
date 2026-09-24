"""Adaptador RBAC de Precios sobre la sesión viva de la aplicación.

POR QUÉ AQUÍ NO HAY TRADUCCIÓN (a diferencia de Proveedores)
------------------------------------------------------------
`SupplierSessionPermissionChecker` traduce sus códigos planos al módulo grueso
`PROVEEDORES`, que la base sí concede. Precios NO puede hacer lo mismo: **no
existe un módulo `PRECIOS`** en `permission_catalog.py` —ni sembrado ni
declarado— así que no hay vocabulario al que traducir. Inventarlo sería
fabricar permisos, y además `tests/unit/pricing/test_pricing_authorization.py::
test_no_coarse_precios_permission` fija hoy que todos los códigos empiecen por
`PRICING_`. Los códigos pasan verbatim.

CONSECUENCIA QUE HAY QUE SABER
------------------------------
`PermissionEvaluator.has_permission()` resuelve, en este orden: bypass de
administrador, comodín global `*`, código exacto, y `MODULO.*`. Para un código
PLANO (`PRICING_LIST_CREATE`) la rama `MODULO.*` no aplica —`split_permission`
lo devuelve sin módulo— y el código exacto no es otorgable desde la matriz de
Configuración, que se construye desde el catálogo.

Resultado real: **sólo el administrador (o quien tenga el comodín global) puede
ejecutar acciones de Precios**. No es un defecto de este archivo: es el estado
del contexto, ya documentado en `frontend/desktop/modules/pricing/
shell_registration.py`. Cerrarlo es convertir el vocabulario a `PRECIOS.accion`
y retirar ese test — una decisión, no una limpieza.
"""

from __future__ import annotations


class PricingSessionPermissionChecker:
    """`PermissionChecker` de `PricingAuthorizationPolicy` sobre la sesión viva.

    Concede sólo cuando la sesión está activa, pertenece al usuario que pide la
    operación, tiene sucursal activa y posee el permiso. Sin sesión / sesión
    inactiva / usuario distinto / sin sucursal / sin `tiene_permiso` → deniega.

    Se exige sucursal activa igual que en Compras y Proveedores: fijar precios
    sin sucursal resuelta dejaría `require_branch` sin contexto que validar.
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
        if not str(getattr(session, "active_branch_id", "") or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))
