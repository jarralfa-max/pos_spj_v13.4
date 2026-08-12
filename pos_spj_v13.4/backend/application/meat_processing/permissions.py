"""Granular Meat Processing permission codes (§50 of the refactor spec).

Never gate a sensitive action with a single general permission. Each one — order
lifecycle transitions, material consumption, weighing, outputs, yield review,
rework, packaging — has its own code, re-validated by the backend on every use
case (hiding a button is not security).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`) so they are stored, granted and checked
exactly like every other bounded context's permissions (Compras, Inventario) —
`rol_permisos`/`usuario_permisos`/`usuario_sucursal_permisos` rows, the
Configuración permission matrix, and `SessionContext.tiene_permiso()` all share
this one vocabulary. Comparisons are case-insensitive (values are normalized to
uppercase at check time).

The module key is `PRODUCCION` — the existing canonical key already used by the
sidebar button (`interfaz/menu_lateral.py`: "Procesamiento Cárnico" → "PRODUCCION")
and already seeded (coarse `ver/crear/editar/eliminar/exportar`) for `admin`,
`gerente` and `almacen` in `migrations/m000_base_schema.py`. Reusing it keeps one
canonical route for this functional area instead of a parallel module key (§3/§64).
"""

from __future__ import annotations


class MeatProcessingPermissions:
    # ── acceso ──────────────────────────────────────────────────────────────
    ACCESS = "PRODUCCION.acceso"
    VIEW = "PRODUCCION.ver"
    VIEW_OWN_BRANCH = "PRODUCCION.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "PRODUCCION.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "PRODUCCION.ver.todas_sucursales"
    EXPORT = "PRODUCCION.exportar"
    AUDIT_VIEW = "PRODUCCION.ver.auditoria"
    DASHBOARD_VIEW = "PRODUCCION.dashboard.ver"

    # ── navegación / secciones del sidebar (§10) — una vista por pestaña,
    # igual que Losses; separadas de los permisos de acción de más abajo ──────
    PREPARATION_VIEW = "PRODUCCION.preparacion.ver"
    ACTIVE_PROCESSING_VIEW = "PRODUCCION.en_proceso.ver"
    CUTTING_VIEW = "PRODUCCION.despiece.ver"
    DERIVED_PRODUCTS_VIEW = "PRODUCCION.derivados.ver"
    PACKAGING_LABELING_VIEW = "PRODUCCION.empaque_etiquetado.ver"
    PRODUCED_LOTS_VIEW = "PRODUCCION.lotes_producidos.ver"
    QUALITY_VIEW = "PRODUCCION.calidad.ver"
    INCIDENTS_VIEW = "PRODUCCION.incidencias.ver"
    TRACEABILITY_VIEW = "PRODUCCION.trazabilidad.ver"
    ALERTS_VIEW = "PRODUCCION.alertas.ver"
    ANALYTICS_VIEW = "PRODUCCION.analisis.ver"

    # ── planeación ──────────────────────────────────────────────────────────
    PLAN_VIEW = "PRODUCCION.plan.ver"
    PLAN_CREATE = "PRODUCCION.plan.crear"
    PLAN_EDIT = "PRODUCCION.plan.editar"
    PLAN_APPROVE = "PRODUCCION.plan.aprobar"
    PLAN_CANCEL = "PRODUCCION.plan.cancelar"

    # ── órdenes ─────────────────────────────────────────────────────────────
    ORDER_VIEW = "PRODUCCION.orden.ver"
    ORDER_CREATE = "PRODUCCION.orden.crear"
    ORDER_EDIT = "PRODUCCION.orden.editar"
    ORDER_APPROVE = "PRODUCCION.orden.aprobar"
    ORDER_RELEASE = "PRODUCCION.orden.liberar"
    ORDER_START = "PRODUCCION.orden.iniciar"
    ORDER_PAUSE = "PRODUCCION.orden.pausar"
    ORDER_RESUME = "PRODUCCION.orden.reanudar"
    ORDER_COMPLETE = "PRODUCCION.orden.completar"
    ORDER_CLOSE = "PRODUCCION.orden.cerrar"
    ORDER_CANCEL = "PRODUCCION.orden.cancelar"
    ORDER_REVERSE = "PRODUCCION.orden.reversar"

    # ── materiales ──────────────────────────────────────────────────────────
    MATERIAL_VIEW = "PRODUCCION.material.ver"
    MATERIAL_ASSIGN = "PRODUCCION.material.asignar"
    CONSUMPTION_CAPTURE = "PRODUCCION.consumo.capturar"
    CONSUMPTION_OVERRIDE = "PRODUCCION.consumo.sobrescribir"
    MATERIAL_SUBSTITUTE = "PRODUCCION.material.sustituir"

    # ── pesajes ─────────────────────────────────────────────────────────────
    WEIGHT_VIEW = "PRODUCCION.peso.ver"
    WEIGHT_CAPTURE = "PRODUCCION.peso.capturar"
    WEIGHT_MANUAL_OVERRIDE = "PRODUCCION.peso.capturar_manual"
    SCALE_MANAGE = "PRODUCCION.bascula.gestionar"

    # ── outputs ─────────────────────────────────────────────────────────────
    OUTPUT_VIEW = "PRODUCCION.output.ver"
    OUTPUT_CAPTURE = "PRODUCCION.output.capturar"
    CO_PRODUCT_CAPTURE = "PRODUCCION.output.coproducto.capturar"
    BY_PRODUCT_CAPTURE = "PRODUCCION.output.subproducto.capturar"
    SUBPRODUCT_CAPTURE = "PRODUCCION.output.derivado.capturar"
    WASTE_CAPTURE = "PRODUCCION.output.merma.capturar"

    # ── rendimientos ────────────────────────────────────────────────────────
    YIELD_VIEW = "PRODUCCION.rendimiento.ver"
    YIELD_REVIEW = "PRODUCCION.rendimiento.revisar"
    YIELD_APPROVE = "PRODUCCION.rendimiento.aprobar"
    YIELD_OVERRIDE = "PRODUCCION.rendimiento.sobrescribir"

    # ── reprocesos ──────────────────────────────────────────────────────────
    REWORK_VIEW = "PRODUCCION.reproceso.ver"
    REWORK_CREATE = "PRODUCCION.reproceso.crear"
    REWORK_APPROVE = "PRODUCCION.reproceso.aprobar"
    REWORK_EXECUTE = "PRODUCCION.reproceso.ejecutar"
    REWORK_CLOSE = "PRODUCCION.reproceso.cerrar"

    # ── empaque ─────────────────────────────────────────────────────────────
    PACKAGING_EXECUTE = "PRODUCCION.empaque.ejecutar"
    LABEL_PRINT = "PRODUCCION.etiqueta.imprimir"
    LABEL_REPRINT = "PRODUCCION.etiqueta.reimprimir"

    # ── configuración ───────────────────────────────────────────────────────
    SETTINGS_VIEW = "PRODUCCION.configuracion.ver"
    SETTINGS_MANAGE = "PRODUCCION.configuracion.editar"
    NOTIFICATIONS_MANAGE = "PRODUCCION.notificacion.gestionar"
    WHATSAPP_ALERTS_MANAGE = "PRODUCCION.whatsapp.gestionar"

    # ── sacrificio futuro (§37/§50) — mismo bounded context, feature-flagged ──
    SLAUGHTER_ACCESS = "PRODUCCION.sacrificio.acceso"
    SLAUGHTER_ANIMAL_RECEPTION = "PRODUCCION.sacrificio.recepcion_animal"
    SLAUGHTER_ANIMAL_LOT_MANAGE = "PRODUCCION.sacrificio.lote_animal.gestionar"
    SLAUGHTER_ORDER_CREATE = "PRODUCCION.sacrificio.orden.crear"
    SLAUGHTER_ORDER_APPROVE = "PRODUCCION.sacrificio.orden.aprobar"
    SLAUGHTER_EXECUTE = "PRODUCCION.sacrificio.ejecutar"
    SLAUGHTER_ANTE_MORTEM_RECORD = "PRODUCCION.sacrificio.ante_mortem.registrar"
    SLAUGHTER_POST_MORTEM_RECORD = "PRODUCCION.sacrificio.post_mortem.registrar"
    SLAUGHTER_CARCASS_CREATE = "PRODUCCION.sacrificio.canal.crear"
    SLAUGHTER_CARCASS_CLASSIFY = "PRODUCCION.sacrificio.canal.clasificar"
    SLAUGHTER_CONDEMNATION_RECORD = "PRODUCCION.sacrificio.decomiso.registrar"
    SLAUGHTER_CHILLING_MANAGE = "PRODUCCION.sacrificio.enfriamiento.gestionar"


ALL_MEAT_PROCESSING_PERMISSIONS = frozenset(
    value for name, value in vars(MeatProcessingPermissions).items()
    if not name.startswith("_") and isinstance(value, str)
)
