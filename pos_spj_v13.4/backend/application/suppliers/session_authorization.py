"""Adaptador RBAC de Proveedores sobre la sesión viva de la aplicación.

POR QUÉ TRADUCE EN VEZ DE COMPARAR DIRECTO
------------------------------------------
`SupplierPermissions.*` usa códigos PLANOS (`SUPPLIERS_ACTIVATE`) que NO están
registrados en `backend/application/security/permission_catalog.py`: Proveedores
figura en su `FLAT_CODE_CONTEXTS`, es decir, sus acciones **no son otorgables**
desde Configuración → Seguridad → Permisos. Lo único que la base concede es el
módulo grueso `PROVEEDORES` con cinco acciones (`ver`, `crear`, `editar`,
`eliminar`, `exportar`), sembradas por `m000_base_schema._seed_system_roles()`.

Sin traducción, cablear este verificador denegaría TODAS las operaciones de
proveedor — el módulo pasaría de "no puedo activar" a "no puedo nada". Se sigue
el mismo patrón que `TransferSessionPermissionChecker`, que existe por esta
misma razón: traducir el puñado de códigos con contrapartida real y denegar el
resto fail-closed.

QUÉ SE PIERDE CON ESTA TRADUCCIÓN (decidido explícitamente, no por descuido)
---------------------------------------------------------------------------
* **Aprobar deja de ser un permiso distinto de editar.** Quien tiene
  `PROVEEDORES.editar` puede enviar a aprobación, aprobar, activar, suspender y
  dar de baja. La granularidad real vuelve el día que Proveedores migre a
  códigos punteados `PROVEEDORES.<accion>` y salga de `FLAT_CODE_CONTEXTS`.
* **La segregación de funciones NO se pierde**: `SupplierApprovalPolicy` compara
  identidades (quien captura no aprueba), y eso es independiente del permiso.
* **Bloquear/desbloquear y verificar cuenta bancaria** se mapean a `eliminar`,
  la acción gruesa más privilegiada, no a `editar`: sacar a un proveedor de
  operación y habilitar que se le pague son decisiones de otro calibre.
* Los códigos de sólo lectura sensibles (`SUPPLIERS_VIEW_FINANCIAL`,
  `..._VIEW_BANK`, `..._VIEW_DOCUMENTS`, `..._VIEW_AUDIT`) quedan SIN mapear y
  por tanto denegados. Hoy es inocuo: ningún caso de uso los exige (los query
  services no pasan por esta política). Mapearlos a `ver` expondría datos
  bancarios y financieros a cualquiera que pueda abrir el módulo.

No añadas entradas nuevas aquí inventando acciones del catálogo: si hace falta
vocabulario nuevo, se registra en `permission_catalog.py` primero.
"""

from __future__ import annotations

#: `SupplierPermissions.*` -> código de catálogo `PROVEEDORES.<accion>` real.
_PERMISSION_MAP = {
    # lectura / alta / edición
    "SUPPLIERS_VIEW": "PROVEEDORES.ver",
    "SUPPLIERS_CREATE": "PROVEEDORES.crear",
    "SUPPLIERS_EDIT": "PROVEEDORES.editar",
    "SUPPLIERS_EXPORT": "PROVEEDORES.exportar",
    # ciclo de vida comercial
    "SUPPLIERS_SUBMIT": "PROVEEDORES.editar",
    "SUPPLIERS_APPROVE": "PROVEEDORES.editar",
    "SUPPLIERS_ACTIVATE": "PROVEEDORES.editar",
    "SUPPLIERS_SUSPEND": "PROVEEDORES.editar",
    "SUPPLIERS_DEACTIVATE": "PROVEEDORES.editar",
    # datos asociados
    "SUPPLIERS_EDIT_TERMS": "PROVEEDORES.editar",
    "SUPPLIERS_EDIT_BANK": "PROVEEDORES.editar",
    "SUPPLIERS_UPLOAD_DOCUMENTS": "PROVEEDORES.editar",
    "SUPPLIERS_EVALUATE": "PROVEEDORES.editar",
    # más privilegiadas: sacan de operación o habilitan pagos
    "SUPPLIERS_BLOCK": "PROVEEDORES.eliminar",
    "SUPPLIERS_UNBLOCK": "PROVEEDORES.eliminar",
    "SUPPLIERS_VERIFY_BANK": "PROVEEDORES.eliminar",
}


class SupplierSessionPermissionChecker:
    """`PermissionChecker` de `SupplierAuthorizationPolicy` sobre la sesión viva.

    Concede sólo cuando la sesión está activa, pertenece al usuario que pide la
    operación, tiene sucursal activa y posee el permiso de catálogo mapeado.
    Sin sesión / sesión inactiva / usuario distinto / sin sucursal / código sin
    mapear / sin `tiene_permiso` → deniega.
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
