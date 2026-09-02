"""Declarative, permission-aware internal navigation for Pedidos y Delivery
(master prompt §68 — a single sidebar entry covering both Order Management
and Last-Mile Fulfillment). Mirrors
`frontend/desktop/modules/losses/navigation/losses_sidebar.py` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions as P


@dataclass(frozen=True, slots=True)
class OrdersDeliveryNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None


ORDERS_DELIVERY_NAV: tuple[OrdersDeliveryNavEntry, ...] = (
    OrdersDeliveryNavEntry("orders_overview", "Resumen", "dashboard", P.DASHBOARD_VIEW,
                           "Indicadores operativos de pedidos y entregas."),
    OrdersDeliveryNavEntry("orders_all", "Todos los pedidos", "list", P.VIEW_OWN_BRANCH,
                           "Listado completo de pedidos de la sucursal."),
    OrdersDeliveryNavEntry("orders_new", "Nuevo pedido", "add", P.ORDER_CREATE,
                           "Capturar un pedido nuevo (mostrador, WhatsApp, teléfono)."),
    OrdersDeliveryNavEntry("orders_scheduled", "Programados", "schedule", P.ORDER_SCHEDULE,
                           "Pedidos programados y su activación.", "scheduled_pending_activation"),
    OrdersDeliveryNavEntry("orders_pending_confirmation", "Pendientes de confirmación",
                           "pending", P.ORDER_CONFIRM,
                           "Pedidos capturados a la espera de confirmación.", "pending_confirmation"),
    OrdersDeliveryNavEntry("orders_preparation", "Preparación", "kitchen", P.PREPARATION_VIEW,
                           "Cola de preparación por pedido.", "preparation_queue"),
    OrdersDeliveryNavEntry("orders_weight_adjustments", "Ajustes de peso", "scale",
                           P.WEIGHT_CAPTURE,
                           "Ajustes de peso pendientes de aprobación.", "weight_adjustments_pending"),
    OrdersDeliveryNavEntry("orders_ready_pickup", "Listos para recoger", "pickup",
                           P.DELIVERY_VIEW, "Pedidos listos para retiro en mostrador."),
    OrdersDeliveryNavEntry("orders_ready_dispatch", "Listos para despacho", "dispatch",
                           P.DISPATCH, "Pedidos listos para salir a ruta."),
    OrdersDeliveryNavEntry("orders_driver_assignment", "Asignación de repartidores", "driver",
                           P.DRIVER_ASSIGN, "Asignar repartidor y vehículo a un pedido."),
    OrdersDeliveryNavEntry("orders_routes", "Rutas", "route", P.ROUTE_PLAN,
                           "Planificación y seguimiento de rutas."),
    OrdersDeliveryNavEntry("orders_active_deliveries", "Entregas activas", "delivery",
                           P.DELIVERY_VIEW, "Entregas en curso.", "active_deliveries"),
    OrdersDeliveryNavEntry("orders_incidents", "Incidencias", "warning", P.FAILURE_REGISTER,
                           "Incidencias registradas durante la entrega.", "open_incidents"),
    OrdersDeliveryNavEntry("orders_failed_deliveries", "Entregas fallidas", "failed",
                           P.FAILURE_REGISTER, "Entregas que no se completaron.", "failed_deliveries"),
    OrdersDeliveryNavEntry("orders_redeliveries", "Reentregas", "redo", P.REDELIVERY_REQUEST,
                           "Solicitudes de reentrega."),
    OrdersDeliveryNavEntry("orders_returns", "Devoluciones", "return", P.RETURN_TO_BRANCH,
                           "Retornos de mercancía a sucursal."),
    OrdersDeliveryNavEntry("orders_cash_collections", "Cobros en ruta", "cash",
                           P.CASH_COLLECTION_RECORD, "Cobros contra entrega registrados por repartidores."),
    OrdersDeliveryNavEntry("orders_settlements", "Liquidaciones", "settlement",
                           P.SETTLEMENT_VIEW, "Corte y conciliación de repartidores.",
                           "settlements_pending_review"),
    OrdersDeliveryNavEntry("orders_tracking", "Seguimiento", "tracking", P.DELIVERY_VIEW,
                           "Seguimiento en tiempo real de pedidos y entregas."),
    OrdersDeliveryNavEntry("orders_alerts", "Alertas", "bell", P.ALERTS_VIEW,
                           "Excepciones críticas del área.", "critical_alerts"),
    OrdersDeliveryNavEntry("orders_analytics", "Análisis", "chart", P.ANALYTICS_VIEW,
                           "Tendencias y desempeño de pedidos y entregas."),
    OrdersDeliveryNavEntry("orders_audit", "Auditoría", "audit", P.VIEW_AUDIT,
                           "Trazabilidad inmutable de pedidos y entregas."),
    OrdersDeliveryNavEntry("orders_settings", "Configuración", "settings", P.SETTINGS_VIEW,
                           "Canales, modalidades, tolerancias, zonas y notificaciones."),
)


def visible_entries(
    has_permission: Callable[[str], bool],
    badges: Mapping[str, int] | None = None,
) -> tuple[tuple[OrdersDeliveryNavEntry, int | None], ...]:
    badges = badges or {}
    return tuple(
        (entry, badges.get(entry.badge_key) if entry.badge_key else None)
        for entry in ORDERS_DELIVERY_NAV
        if has_permission(entry.permission)
    )
