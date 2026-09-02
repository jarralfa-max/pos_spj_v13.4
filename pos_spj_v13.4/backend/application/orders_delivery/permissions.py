"""Granular Pedidos/Delivery permission codes (master prompt §63).

Never gate order/delivery actions with a single general permission. Order
capture, confirmation, scheduling, preparation, catch-weight adjustment,
customer approval, substitution, packaging, driver assignment, routing,
dispatch, delivery confirmation, failed-delivery/redelivery, cash-on-delivery
collection and driver settlement each have their own code. The backend
re-validates every one (hiding a button is not security — master prompt
§62).

Codes use the app-wide canonical `MODULO.accion` format (see
`core/security/permission_catalog.py`) so they are stored, granted and
checked exactly like every other module's permissions. Pedidos and Delivery
share the single existing `DELIVERY` catalog key — one nav entry, one
permission namespace (master prompt §68: "PEDIDOS Y DELIVERY" is one sidebar
entry) — never a parallel `ORDERS`/`PEDIDOS` key. Comparisons are
case-insensitive (values are normalized to uppercase at check time).
"""

from __future__ import annotations


class OrdersDeliveryPermissions:
    # ── acceso (§63) ──────────────────────────────────────────────────────
    ACCESS = "DELIVERY.acceso"
    DASHBOARD_VIEW = "DELIVERY.dashboard.ver"
    VIEW_OWN_BRANCH = "DELIVERY.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "DELIVERY.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "DELIVERY.ver.todas_sucursales"
    EXPORT = "DELIVERY.exportar"
    VIEW_AUDIT = "DELIVERY.auditoria.ver"
    ALERTS_VIEW = "DELIVERY.alertas.ver"
    ANALYTICS_VIEW = "DELIVERY.analisis.ver"

    # ── pedidos (§63 "Pedidos") ──────────────────────────────────────────
    ORDER_CREATE = "DELIVERY.pedido.crear"
    ORDER_EDIT_DRAFT = "DELIVERY.pedido.editar_borrador"
    ORDER_CONFIRM = "DELIVERY.pedido.confirmar"
    ORDER_SCHEDULE = "DELIVERY.pedido.programar"
    ORDER_RESCHEDULE = "DELIVERY.pedido.reprogramar"
    ORDER_CANCEL = "DELIVERY.pedido.cancelar"
    ORDER_REVERSE = "DELIVERY.pedido.reversar"

    # ── preparación (§63 "Preparación") ─────────────────────────────────
    PREPARATION_VIEW = "DELIVERY.preparacion.ver"
    PREPARATION_ASSIGN = "DELIVERY.preparacion.asignar"
    PREPARATION_START = "DELIVERY.preparacion.iniciar"
    PREPARATION_COMPLETE = "DELIVERY.preparacion.completar"
    WEIGHT_CAPTURE = "DELIVERY.peso.capturar"
    WEIGHT_OVERRIDE = "DELIVERY.peso.sobrescribir"
    SUBSTITUTION_PROPOSE = "DELIVERY.sustitucion.proponer"

    # ── aprobación del cliente (§63 "Aprobación del cliente") ───────────
    CUSTOMER_APPROVAL_VIEW = "DELIVERY.aprobacion_cliente.ver"
    CUSTOMER_APPROVAL_RESEND = "DELIVERY.aprobacion_cliente.reenviar"
    CUSTOMER_APPROVAL_OVERRIDE = "DELIVERY.aprobacion_cliente.sobrescribir"

    # ── delivery / última milla (§63 "Delivery") ────────────────────────
    DELIVERY_VIEW = "DELIVERY.entrega.ver"
    DELIVERY_CREATE = "DELIVERY.entrega.crear"
    DRIVER_ASSIGN = "DELIVERY.repartidor.asignar"
    ROUTE_PLAN = "DELIVERY.ruta.planificar"
    DISPATCH = "DELIVERY.despacho.ejecutar"
    ARRIVAL_CONFIRM = "DELIVERY.llegada.confirmar"
    DELIVERY_CONFIRM = "DELIVERY.entrega.confirmar"
    FAILURE_REGISTER = "DELIVERY.falla.registrar"
    REDELIVERY_REQUEST = "DELIVERY.reentrega.solicitar"
    RETURN_TO_BRANCH = "DELIVERY.retorno_sucursal.registrar"
    DELIVERY_REVERSE = "DELIVERY.entrega.reversar"

    # ── repartidores (§63 "Repartidores") ───────────────────────────────
    DRIVER_VIEW = "DELIVERY.repartidor.ver"
    DRIVER_STATUS_MANAGE = "DELIVERY.repartidor.estado_gestionar"
    DRIVER_CASH_VIEW = "DELIVERY.repartidor.efectivo_ver"

    # ── cobro y liquidación (§63 "Cobro y liquidación") ─────────────────
    CASH_COLLECTION_RECORD = "DELIVERY.cobro.registrar"
    CASH_COLLECTION_OVERRIDE = "DELIVERY.cobro.sobrescribir"
    SETTLEMENT_VIEW = "DELIVERY.liquidacion.ver"
    SETTLEMENT_CREATE = "DELIVERY.liquidacion.crear"
    SETTLEMENT_REVIEW = "DELIVERY.liquidacion.revisar"
    SETTLEMENT_APPROVE = "DELIVERY.liquidacion.aprobar"
    SETTLEMENT_CLOSE = "DELIVERY.liquidacion.cerrar"

    # ── configuración (§63 "Configuración") ─────────────────────────────
    SETTINGS_VIEW = "DELIVERY.configuracion.ver"
    SETTINGS_MANAGE = "DELIVERY.configuracion.editar"
    NOTIFICATIONS_MANAGE = "DELIVERY.notificacion.gestionar"
    WHATSAPP_MANAGE = "DELIVERY.whatsapp.gestionar"


ALL_ORDERS_DELIVERY_PERMISSIONS = frozenset(
    v for k, v in vars(OrdersDeliveryPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
