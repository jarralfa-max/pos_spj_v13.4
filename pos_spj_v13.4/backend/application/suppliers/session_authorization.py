"""Adaptador RBAC de Proveedores sobre la sesión viva de la aplicación.

Auditoría de permisos 968e0bc (PER-04): `SupplierPermissions.*` dejó de ser un
código PLANO (`SUPPLIERS_ACTIVATE`) y es `PROVEEDORES.<accion>`, registrado en el
catálogo y otorgable desde Configuración → Seguridad → Permisos. Se concede en
este orden:

1. El código granular, tal cual (`PROVEEDORES.aprobar`).
2. Si no, la acción GRUESA que lo traducía antes (abajo) — se conserva porque
   fue decisión del usuario (2026-09-16) y los roles sembrados sólo tienen las
   cinco acciones gruesas: quitarla dejaría a gerente y almacén sin módulo.

QUÉ SIGUE PERDIÉNDOSE CON EL RESPALDO GRUESO (decidido, no por descuido)
------------------------------------------------------------------------
* Quien tiene `PROVEEDORES.editar` puede enviar a aprobación, aprobar, activar,
  suspender y dar de baja. Para separar esas funciones, se le quita `editar` al
  rol y se conceden los códigos granulares que correspondan.
* La segregación de funciones NO se pierde: `SupplierApprovalPolicy` compara
  identidades (quien captura no aprueba), y eso es independiente del permiso.
* Bloquear/desbloquear y verificar cuenta bancaria se respaldan en `eliminar`,
  la acción gruesa más privilegiada: sacar a un proveedor de operación y
  habilitar que se le pague son decisiones de otro calibre.
* Las lecturas sensibles (`finanzas.ver`, `banco.ver`, `documentos.ver`,
  `auditoria.ver`) NO tienen respaldo grueso: sólo con su código granular.
"""

from __future__ import annotations

from backend.application.suppliers.permissions import SupplierPermissions as P

#: Respaldo grueso: código granular → acción gruesa sembrada que lo concede.
#: `ver`/`crear`/`editar`/`exportar` no aparecen: el código granular ES el grueso.
COARSE_FALLBACK = {
    # ciclo de vida comercial
    P.SUBMIT: "PROVEEDORES.editar",
    P.APPROVE: "PROVEEDORES.editar",
    P.ACTIVATE: "PROVEEDORES.editar",
    P.SUSPEND: "PROVEEDORES.editar",
    P.DEACTIVATE: "PROVEEDORES.editar",
    # datos asociados
    P.EDIT_TERMS: "PROVEEDORES.editar",
    P.EDIT_BANK: "PROVEEDORES.editar",
    P.UPLOAD_DOCUMENTS: "PROVEEDORES.editar",
    P.EVALUATE: "PROVEEDORES.editar",
    # más privilegiadas: sacan de operación o habilitan pagos
    P.BLOCK: "PROVEEDORES.eliminar",
    P.UNBLOCK: "PROVEEDORES.eliminar",
    P.VERIFY_BANK: "PROVEEDORES.eliminar",
}


class SupplierSessionPermissionChecker:
    """`PermissionChecker` de `SupplierAuthorizationPolicy` sobre la sesión viva.

    Concede sólo cuando la sesión está activa, pertenece al usuario que pide la
    operación, tiene sucursal activa y posee el código granular o su respaldo
    grueso. Sin sesión / sesión inactiva / usuario distinto / sin sucursal /
    sin `tiene_permiso` → deniega.
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
