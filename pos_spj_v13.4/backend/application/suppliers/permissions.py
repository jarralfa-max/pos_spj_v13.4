"""Granular supplier permission codes (FASE SUP-3 / §28) — ``PROVEEDORES.<accion>``.

Never gate the module with a single general permission — each sensitive action
has its own code (financial data, bank data, verification, audit, export…).

Auditoría de permisos 968e0bc (PER-04): eran códigos planos (``SUPPLIERS_*``)
que la matriz de Configuración no podía conceder. ``ver``/``crear``/``editar``/
``exportar`` coinciden con las acciones gruesas sembradas; el resto es granular
y otorgable. La traducción grueso→fino que decidió el usuario (2026-09-16) se
conserva en ``session_authorization.py`` como respaldo.
"""

from __future__ import annotations


class SupplierPermissions:
    VIEW = "PROVEEDORES.ver"
    CREATE = "PROVEEDORES.crear"
    EDIT = "PROVEEDORES.editar"
    SUBMIT = "PROVEEDORES.enviar"
    APPROVE = "PROVEEDORES.aprobar"
    ACTIVATE = "PROVEEDORES.activar"
    SUSPEND = "PROVEEDORES.suspender"
    DEACTIVATE = "PROVEEDORES.baja"
    BLOCK = "PROVEEDORES.bloquear"
    UNBLOCK = "PROVEEDORES.desbloquear"
    VIEW_FINANCIAL = "PROVEEDORES.finanzas.ver"
    EDIT_TERMS = "PROVEEDORES.condiciones.editar"
    VIEW_BANK = "PROVEEDORES.banco.ver"
    EDIT_BANK = "PROVEEDORES.banco.editar"
    VERIFY_BANK = "PROVEEDORES.banco.verificar"
    VIEW_DOCUMENTS = "PROVEEDORES.documentos.ver"
    UPLOAD_DOCUMENTS = "PROVEEDORES.documentos.cargar"
    EVALUATE = "PROVEEDORES.evaluar"
    EXPORT = "PROVEEDORES.exportar"
    VIEW_AUDIT = "PROVEEDORES.auditoria.ver"


ALL_SUPPLIER_PERMISSIONS = frozenset(
    v for k, v in vars(SupplierPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
