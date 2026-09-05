"""Granular Assets/EAM permission codes (§71-82).

Never gate Activos with a single general permission. Each sensitive action —
custody, transfer, maintenance work order, inspection, capitalization
proposal, physical inventory, disposal, tagging — has its own code, and the
backend re-validates every one (hiding a button is not security, §84-85).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`), replacing the legacy flat
``"ACTIVOS": ["ver", "crear", "mantenimiento"]`` stub in place — same
transformation COMPRAS/INVENTARIO/FINANZAS already went through (see
[[feedback_permissions_compras_standard]]). Comparisons are case-insensitive.

Deliberately absent: any permission to post journal entries or execute
treasury payments from Activos — that boundary belongs to FINANZAS
(`docs/refactor/assets_finance_boundary_map.md`, §77, §84).
"""

from __future__ import annotations


class AssetPermissions:
    # ── acceso general (§71) ────────────────────────────────────────────────
    VIEW = "ACTIVOS.ver"
    DASHBOARD_VIEW = "ACTIVOS.ver.dashboard"
    GLOBAL_SEARCH = "ACTIVOS.ver.busqueda_global"
    AUDIT_VIEW = "ACTIVOS.ver.auditoria"
    SETTINGS_VIEW = "ACTIVOS.configuracion.ver"
    SETTINGS_MANAGE = "ACTIVOS.configuracion.editar"

    # ── activos (§72) ────────────────────────────────────────────────────────
    VIEW_OWN = "ACTIVOS.ver.propios"
    VIEW_BRANCH = "ACTIVOS.ver.sucursal"
    VIEW_COMPANY = "ACTIVOS.ver.empresa"
    CREATE = "ACTIVOS.crear"
    EDIT = "ACTIVOS.editar"
    EDIT_SENSITIVE = "ACTIVOS.editar.sensible"
    COMMISSION = "ACTIVOS.comisionar"
    SUSPEND = "ACTIVOS.suspender"
    REACTIVATE = "ACTIVOS.reactivar"
    CHANGE_CONDITION = "ACTIVOS.condicion.cambiar"

    # ── custodia (§73) ───────────────────────────────────────────────────────
    CUSTODY_VIEW = "ACTIVOS.custodia.ver"
    ASSIGN = "ACTIVOS.custodia.asignar"
    REASSIGN = "ACTIVOS.custodia.reasignar"
    RETURN = "ACTIVOS.custodia.devolver"
    LOAN_CREATE = "ACTIVOS.prestamo.crear"
    LOAN_RETURN = "ACTIVOS.prestamo.devolver"
    CUSTODY_HISTORY_VIEW = "ACTIVOS.custodia.historial"

    # ── transferencias (§74) ─────────────────────────────────────────────────
    TRANSFER_VIEW = "ACTIVOS.transferencia.ver"
    TRANSFER_REQUEST = "ACTIVOS.transferencia.solicitar"
    TRANSFER_APPROVE = "ACTIVOS.transferencia.aprobar"
    TRANSFER_PREPARE = "ACTIVOS.transferencia.preparar"
    TRANSFER_SHIP = "ACTIVOS.transferencia.enviar"
    TRANSFER_RECEIVE = "ACTIVOS.transferencia.recibir"
    TRANSFER_REJECT = "ACTIVOS.transferencia.rechazar"
    TRANSFER_CANCEL = "ACTIVOS.transferencia.cancelar"

    # ── mantenimiento (§75) ──────────────────────────────────────────────────
    MAINTENANCE_VIEW = "ACTIVOS.mantenimiento.ver"
    MAINTENANCE_PLAN_VIEW = "ACTIVOS.mantenimiento.plan.ver"
    MAINTENANCE_PLAN_CREATE = "ACTIVOS.mantenimiento.plan.crear"
    MAINTENANCE_PLAN_EDIT = "ACTIVOS.mantenimiento.plan.editar"
    WORK_ORDER_VIEW = "ACTIVOS.mantenimiento.orden.ver"
    WORK_ORDER_CREATE = "ACTIVOS.mantenimiento.orden.crear"
    WORK_ORDER_APPROVE = "ACTIVOS.mantenimiento.orden.aprobar"
    WORK_ORDER_ASSIGN = "ACTIVOS.mantenimiento.orden.asignar"
    WORK_ORDER_START = "ACTIVOS.mantenimiento.orden.iniciar"
    WORK_ORDER_PAUSE = "ACTIVOS.mantenimiento.orden.pausar"
    WORK_ORDER_COMPLETE = "ACTIVOS.mantenimiento.orden.completar"
    WORK_ORDER_CLOSE = "ACTIVOS.mantenimiento.orden.cerrar"
    WORK_ORDER_CANCEL = "ACTIVOS.mantenimiento.orden.cancelar"
    MAINTENANCE_COST_VIEW = "ACTIVOS.mantenimiento.costo.ver"
    MAINTENANCE_COST_EDIT = "ACTIVOS.mantenimiento.costo.editar"

    # ── inspección (§76) ─────────────────────────────────────────────────────
    INSPECTION_VIEW = "ACTIVOS.inspeccion.ver"
    INSPECTION_CREATE = "ACTIVOS.inspeccion.crear"
    INSPECTION_EXECUTE = "ACTIVOS.inspeccion.ejecutar"
    INSPECTION_APPROVE = "ACTIVOS.inspeccion.aprobar"
    INSPECTION_OVERRIDE = "ACTIVOS.inspeccion.anular"

    # ── costos / frontera financiera de solo lectura y propuesta (§77) ──────
    # Nunca ACTIVOS.asiento.* ni ACTIVOS.tesoreria.* — esa frontera es de
    # FINANZAS (ver docs/refactor/assets_finance_boundary_map.md).
    COST_VIEW = "ACTIVOS.costo.ver"
    FINANCIAL_PROJECTION_VIEW = "ACTIVOS.proyeccion_financiera.ver"
    CAPITALIZATION_PROPOSAL_VIEW = "ACTIVOS.capitalizacion.ver"
    CAPITALIZATION_PROPOSAL_CREATE = "ACTIVOS.capitalizacion.proponer"
    CAPITALIZATION_PROPOSAL_SUBMIT = "ACTIVOS.capitalizacion.enviar"
    CAPITALIZATION_PROPOSAL_CANCEL = "ACTIVOS.capitalizacion.cancelar"

    # ── inventario físico (§78) ──────────────────────────────────────────────
    PHYSICAL_INVENTORY_VIEW = "ACTIVOS.inventario_fisico.ver"
    PHYSICAL_INVENTORY_CREATE = "ACTIVOS.inventario_fisico.crear"
    PHYSICAL_INVENTORY_COUNT = "ACTIVOS.inventario_fisico.contar"
    PHYSICAL_INVENTORY_COMPLETE = "ACTIVOS.inventario_fisico.completar"
    DISCREPANCY_VIEW = "ACTIVOS.diferencia.ver"
    DISCREPANCY_RESOLVE = "ACTIVOS.diferencia.resolver"

    # ── documentación (§79) ──────────────────────────────────────────────────
    DOCUMENT_VIEW = "ACTIVOS.documento.ver"
    DOCUMENT_UPLOAD = "ACTIVOS.documento.subir"
    DOCUMENT_DOWNLOAD = "ACTIVOS.documento.descargar"
    DOCUMENT_DELETE = "ACTIVOS.documento.eliminar"
    WARRANTY_VIEW = "ACTIVOS.garantia.ver"
    WARRANTY_MANAGE = "ACTIVOS.garantia.gestionar"
    INSURANCE_VIEW = "ACTIVOS.seguro.ver"
    INSURANCE_MANAGE = "ACTIVOS.seguro.gestionar"

    # ── bajas (§80) ───────────────────────────────────────────────────────────
    DISPOSAL_VIEW = "ACTIVOS.baja.ver"
    DISPOSAL_REQUEST = "ACTIVOS.baja.solicitar"
    DISPOSAL_REVIEW = "ACTIVOS.baja.revisar"
    DISPOSAL_APPROVE = "ACTIVOS.baja.aprobar"
    DISPOSAL_REJECT = "ACTIVOS.baja.rechazar"
    DISPOSAL_EXECUTE = "ACTIVOS.baja.ejecutar"
    DISPOSAL_CANCEL = "ACTIVOS.baja.cancelar"

    # ── etiquetas / QR (§81) ─────────────────────────────────────────────────
    TAG_VIEW = "ACTIVOS.etiqueta.ver"
    TAG_CREATE = "ACTIVOS.etiqueta.crear"
    TAG_PRINT = "ACTIVOS.etiqueta.imprimir"
    TAG_REPRINT = "ACTIVOS.etiqueta.reimprimir"
    TAG_REPLACE = "ACTIVOS.etiqueta.reemplazar"


ALL_ASSET_PERMISSIONS = frozenset(
    v for k, v in vars(AssetPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
