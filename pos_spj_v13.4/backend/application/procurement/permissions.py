"""Granular procurement permission codes (§55-62).

Never gate purchasing with a single general permission. Each sensitive action —
direct purchase, financial treatment, requisitions, quotes, orders, receiving,
invoicing — has its own code. The backend re-validates every one (hiding a
button is not security).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`) so they are stored, granted and checked
exactly like every other module's permissions — `rol_permisos` rows, the
Configuración permission matrix and `SessionContext.tiene_permiso()` all share
this one vocabulary. Comparisons are case-insensitive (values are normalized to
uppercase at check time), so codes are authored in the same mixed-case style as
the rest of the catalog (e.g. `FINANZAS.asiento.crear`).
"""

from __future__ import annotations


class PurchasePermissions:
    # ── consulta (§55) ────────────────────────────────────────────────────
    VIEW = "COMPRAS.ver"
    VIEW_OWN_BRANCH = "COMPRAS.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "COMPRAS.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "COMPRAS.ver.todas_sucursales"
    VIEW_COSTS = "COMPRAS.ver.costos"
    VIEW_MARGINS = "COMPRAS.ver.margenes"
    VIEW_PAYMENTS = "COMPRAS.ver.pagos"
    VIEW_SUPPLIER_CREDIT = "COMPRAS.ver.credito_proveedor"
    VIEW_AUDIT = "COMPRAS.ver.auditoria"
    VIEW_ANALYTICS = "COMPRAS.ver.analitica"
    EXPORT = "COMPRAS.exportar"

    # ── compra directa (§56) ──────────────────────────────────────────────
    DIRECT_VIEW = "COMPRAS.directa.ver"
    DIRECT_CREATE = "COMPRAS.directa.crear"
    DIRECT_EDIT = "COMPRAS.directa.editar"
    DIRECT_CONFIRM = "COMPRAS.directa.confirmar"
    DIRECT_SAVE_DRAFT = "COMPRAS.directa.guardar_borrador"
    DIRECT_USE_OCCASIONAL_SUPPLIER = "COMPRAS.directa.proveedor_ocasional"
    DIRECT_CREATE_PRODUCT = "COMPRAS.directa.crear_producto"
    DIRECT_OVERRIDE_PRICE = "COMPRAS.directa.sobrescribir_precio"
    DIRECT_OVERRIDE_COST = "COMPRAS.directa.sobrescribir_costo"
    DIRECT_OVER_RECEIVE = "COMPRAS.directa.sobre_recibir"
    DIRECT_CANCEL = "COMPRAS.directa.cancelar"
    DIRECT_REVERSE = "COMPRAS.directa.reversar"
    DIRECT_PRINT = "COMPRAS.directa.imprimir"

    # ── financieros (§57) ─────────────────────────────────────────────────
    REQUEST_IMMEDIATE_PAYMENT = "COMPRAS.pago.inmediato"
    REQUEST_PETTY_CASH_PAYMENT = "COMPRAS.pago.caja_chica"
    REQUEST_TREASURY_PAYMENT = "COMPRAS.pago.tesoreria"
    REQUEST_BANK_TRANSFER = "COMPRAS.pago.transferencia"
    USE_SUPPLIER_CREDIT = "COMPRAS.credito_proveedor.usar"
    USE_ADVANCE = "COMPRAS.anticipo.usar"
    USE_MIXED_TERMS = "COMPRAS.condiciones.mixtas"
    OVERRIDE_FINANCIAL_LIMIT = "COMPRAS.limite.sobrescribir"
    VIEW_PAYMENT_REFERENCE = "COMPRAS.pago.ver_referencia"

    # ── solicitudes (§58) ─────────────────────────────────────────────────
    REQUISITION_VIEW = "COMPRAS.solicitud.ver"
    REQUISITION_CREATE = "COMPRAS.solicitud.crear"
    REQUISITION_EDIT = "COMPRAS.solicitud.editar"
    REQUISITION_SUBMIT = "COMPRAS.solicitud.enviar"
    REQUISITION_APPROVE = "COMPRAS.solicitud.aprobar"
    REQUISITION_REJECT = "COMPRAS.solicitud.rechazar"
    REQUISITION_CANCEL = "COMPRAS.solicitud.cancelar"

    # ── cotizaciones (§59) ────────────────────────────────────────────────
    RFQ_CREATE = "COMPRAS.rfq.crear"
    RFQ_SEND = "COMPRAS.rfq.enviar"
    QUOTE_CAPTURE = "COMPRAS.cotizacion.capturar"
    QUOTE_EDIT = "COMPRAS.cotizacion.editar"
    QUOTE_COMPARE = "COMPRAS.cotizacion.comparar"
    QUOTE_AWARD = "COMPRAS.cotizacion.adjudicar"
    QUOTE_OVERRIDE_SELECTION = "COMPRAS.cotizacion.sobrescribir_seleccion"

    # ── órdenes (§60) ─────────────────────────────────────────────────────
    ORDER_VIEW = "COMPRAS.orden.ver"
    ORDER_CREATE = "COMPRAS.orden.crear"
    ORDER_EDIT = "COMPRAS.orden.editar"
    ORDER_SUBMIT = "COMPRAS.orden.enviar_aprobacion"
    ORDER_APPROVE = "COMPRAS.orden.aprobar"
    ORDER_SEND = "COMPRAS.orden.enviar"
    ORDER_ACKNOWLEDGE = "COMPRAS.orden.confirmar"
    ORDER_CHANGE_APPROVED = "COMPRAS.orden.versionar"
    ORDER_CANCEL = "COMPRAS.orden.cancelar"
    ORDER_CLOSE = "COMPRAS.orden.cerrar"

    # ── recepción (§61) ───────────────────────────────────────────────────
    RECEIPT_VIEW = "COMPRAS.recepcion.ver"
    RECEIPT_CREATE = "COMPRAS.recepcion.crear"
    RECEIPT_DIRECT = "COMPRAS.recepcion.directa"
    RECEIPT_COMPLETE = "COMPRAS.recepcion.completar"
    RECEIPT_PARTIAL = "COMPRAS.recepcion.parcial"
    RECEIPT_OVER_TOLERANCE = "COMPRAS.recepcion.tolerancia"
    RECEIPT_MANUAL_WEIGHT = "COMPRAS.recepcion.peso_manual"
    RECEIPT_REJECT = "COMPRAS.recepcion.rechazar"
    RECEIPT_REVERSE = "COMPRAS.recepcion.reversar"
    QUALITY_INSPECT = "COMPRAS.calidad.inspeccionar"
    QUALITY_RELEASE = "COMPRAS.calidad.liberar"
    QUARANTINE = "COMPRAS.recepcion.cuarentena"
    RETURN = "COMPRAS.recepcion.devolucion"

    # ── facturas y conciliación (§62) ─────────────────────────────────────
    INVOICE_VIEW = "COMPRAS.factura.ver"
    INVOICE_CAPTURE = "COMPRAS.factura.capturar"
    INVOICE_EDIT = "COMPRAS.factura.editar"
    INVOICE_MATCH = "COMPRAS.factura.conciliar"
    INVOICE_RELEASE_VARIANCE = "COMPRAS.factura.liberar_diferencia"
    INVOICE_BLOCK = "COMPRAS.factura.bloquear"
    INVOICE_CANCEL = "COMPRAS.factura.cancelar"


ALL_PURCHASE_PERMISSIONS = frozenset(
    v for k, v in vars(PurchasePermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
