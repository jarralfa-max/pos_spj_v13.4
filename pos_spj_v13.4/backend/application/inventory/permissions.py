"""Granular inventory permission codes (§45-49).

Inventory is never gated by a single ``INVENTARIO`` permission. Every sensitive
action — movement, adjustment, transfer approval/dispatch/receipt, count
confirm, quarantine release, manual weight override — has its own code, and the
backend re-validates each one on every use case (hiding a button is not
security).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`) so they are stored, granted and checked
exactly like every other module's permissions — `rol_permisos` rows, the
Configuración permission matrix and `SessionContext.tiene_permiso()` all share
this one vocabulary. Comparisons are case-insensitive (values are normalized to
uppercase at check time), so codes are authored in the same mixed-case style as
the rest of the catalog (e.g. `COMPRAS.directa.crear`).

Transfer *lifecycle* permissions (request/approve/dispatch/receive) belong to
the Transferencias bounded context (`TRANSFERENCIAS.*` / the future granular
`TransferPermissions`, see docs/refactor/TRF-0_transfers_audit_and_plan.md) —
Inventario never re-implements that workflow. The only inventory-owned
transfer-adjacent permission is ``IN_TRANSIT_VIEW`` (read-only visibility of
stock currently in transit).
"""

from __future__ import annotations


class InventoryPermissions:
    # ── consulta (§46) ────────────────────────────────────────────────────
    ACCESS = "INVENTARIO.acceso"
    VIEW = "INVENTARIO.ver"
    VIEW_OWN_BRANCH = "INVENTARIO.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "INVENTARIO.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "INVENTARIO.ver.todas_sucursales"
    VIEW_COST_REFERENCE = "INVENTARIO.ver.costo_referencia"
    VIEW_TRACEABILITY = "INVENTARIO.ver.trazabilidad"
    TRACEABILITY_LINK = "INVENTARIO.trazabilidad.vincular"
    VIEW_AUDIT = "INVENTARIO.ver.auditoria"
    EXPORT = "INVENTARIO.exportar"

    # ── almacenes y ubicaciones (§46) ─────────────────────────────────────
    WAREHOUSE_VIEW = "INVENTARIO.almacen.ver"
    WAREHOUSE_CREATE = "INVENTARIO.almacen.crear"
    WAREHOUSE_EDIT = "INVENTARIO.almacen.editar"
    WAREHOUSE_ACTIVATE = "INVENTARIO.almacen.activar"
    WAREHOUSE_BLOCK = "INVENTARIO.almacen.bloquear"
    WAREHOUSE_DEACTIVATE = "INVENTARIO.almacen.desactivar"
    LOCATION_VIEW = "INVENTARIO.ubicacion.ver"
    LOCATION_MANAGE = "INVENTARIO.ubicacion.gestionar"

    # ── movimientos (§46) ─────────────────────────────────────────────────
    MOVEMENT_VIEW = "INVENTARIO.movimiento.ver"
    MOVEMENT_CREATE = "INVENTARIO.movimiento.crear_manual"
    MOVEMENT_REVERSE = "INVENTARIO.movimiento.reversar"
    MOVEMENT_OVERRIDE = "INVENTARIO.movimiento.sobrescribir"

    # ── lotes y series (§46) ──────────────────────────────────────────────
    LOT_VIEW = "INVENTARIO.lote.ver"
    LOT_CREATE = "INVENTARIO.lote.crear"
    LOT_EDIT = "INVENTARIO.lote.editar"
    LOT_BLOCK = "INVENTARIO.lote.bloquear"
    LOT_RELEASE = "INVENTARIO.lote.liberar"
    SERIAL_MANAGE = "INVENTARIO.serie.gestionar"

    # ── reservas (§46) ────────────────────────────────────────────────────
    RESERVATION_VIEW = "INVENTARIO.reserva.ver"
    RESERVATION_CREATE = "INVENTARIO.reserva.crear"
    RESERVATION_RELEASE = "INVENTARIO.reserva.liberar"
    ALLOCATION_OVERRIDE = "INVENTARIO.reserva.sobrescribir_asignacion"

    # ── inventario en tránsito (§10/§41 — workflow vive en TRANSFERENCIAS.*) ──
    IN_TRANSIT_VIEW = "INVENTARIO.transito.ver"

    # ── conteos (§46) ─────────────────────────────────────────────────────
    COUNT_VIEW = "INVENTARIO.conteo.ver"
    COUNT_CREATE = "INVENTARIO.conteo.crear"
    COUNT_EXECUTE = "INVENTARIO.conteo.ejecutar"
    COUNT_CONFIRM = "INVENTARIO.conteo.confirmar"
    COUNT_RECOUNT = "INVENTARIO.conteo.recontar"
    COUNT_APPROVE = "INVENTARIO.conteo.aprobar"
    COUNT_VIEW_EXPECTED = "INVENTARIO.conteo.ver_esperado"

    # ── ajustes (§46) ─────────────────────────────────────────────────────
    ADJUSTMENT_VIEW = "INVENTARIO.ajuste.ver"
    ADJUSTMENT_CREATE = "INVENTARIO.ajuste.crear"
    ADJUSTMENT_APPROVE = "INVENTARIO.ajuste.aprobar"
    ADJUSTMENT_POST = "INVENTARIO.ajuste.postear"
    ADJUSTMENT_REVERSE = "INVENTARIO.ajuste.reversar"

    # ── calidad y cuarentena (§46) ────────────────────────────────────────
    QUARANTINE_VIEW = "INVENTARIO.cuarentena.ver"
    QUARANTINE_CREATE = "INVENTARIO.cuarentena.crear"
    QUARANTINE_RELEASE = "INVENTARIO.cuarentena.liberar"
    QUALITY_BLOCK = "INVENTARIO.calidad.bloquear"
    QUALITY_RELEASE = "INVENTARIO.calidad.liberar"
    DISPOSAL_AUTHORIZE = "INVENTARIO.cuarentena.disponer"

    # ── peso y báscula (§46) ──────────────────────────────────────────────
    WEIGHT_CAPTURE = "INVENTARIO.peso.capturar"
    WEIGHT_MANUAL_OVERRIDE = "INVENTARIO.peso.capturar_manual"
    SCALE_USE = "INVENTARIO.bascula.usar"
    SCALE_MANAGE = "INVENTARIO.bascula.gestionar"
    LABEL_PRINT = "INVENTARIO.lote.imprimir"
    LABEL_REPRINT = "INVENTARIO.lote.reimprimir"

    # ── recepciones físicas (§32) ─────────────────────────────────────────
    RECEIPT_VIEW = "INVENTARIO.recepcion.ver"
    RECEIPT_INSPECT = "INVENTARIO.recepcion.inspeccionar"
    RECEIPT_REVERSE = "INVENTARIO.recepcion.reversar"

    # ── reposición (§34) ──────────────────────────────────────────────────
    REPLENISHMENT_VIEW = "INVENTARIO.reposicion.ver"
    REPLENISHMENT_MANAGE = "INVENTARIO.reposicion.configurar"
    REPLENISHMENT_GENERATE = "INVENTARIO.reposicion.generar"

    # ── negativo (override) (§16) ─────────────────────────────────────────
    NEGATIVE_OVERRIDE = "INVENTARIO.movimiento.permitir_negativo"

    # ── cadena de frío (§21) ──────────────────────────────────────────────
    TEMPERATURE_VIEW = "INVENTARIO.temperatura.ver"
    TEMPERATURE_RECORD = "INVENTARIO.temperatura.registrar"
    TEMPERATURE_RESOLVE = "INVENTARIO.temperatura.resolver"

    # ── configuración (§46) ───────────────────────────────────────────────
    SETTINGS_VIEW = "INVENTARIO.configuracion.ver"
    SETTINGS_MANAGE = "INVENTARIO.configuracion.editar"
    NOTIFICATIONS_MANAGE = "INVENTARIO.notificacion.gestionar"
    WHATSAPP_ALERTS_MANAGE = "INVENTARIO.whatsapp.gestionar"


ALL_INVENTORY_PERMISSIONS = frozenset(
    v for k, v in vars(InventoryPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
