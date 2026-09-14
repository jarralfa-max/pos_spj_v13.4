"""Canonical, permission-aware information architecture for desktop Purchasing."""

from __future__ import annotations

from dataclasses import dataclass

from frontend.desktop.components.icons import Icons


class PurchasingRoutes:
    DASHBOARD = "dashboard"
    REQUISITIONS = "requisitions"
    QUOTATIONS = "quotations"
    ORDERS = "orders"
    DIRECT_PURCHASE_CREATE = "direct_purchase_create"
    DIRECT_PURCHASE_HISTORY = "direct_purchase_history"
    ORIGIN_LOADING = "origin_loading"
    RECEIPTS = "receipts"
    INVOICES = "invoices"


@dataclass(frozen=True)
class PurchasingRouteDefinition:
    key: str
    label: str
    group: str
    capability: str
    icon: str
    badge_key: str | None = None


IMPLEMENTED_PURCHASING_ROUTES = (
    PurchasingRouteDefinition(PurchasingRoutes.DASHBOARD, "Resumen", "COMPRAS",
                              "module_view", Icons.DASHBOARD),
    PurchasingRouteDefinition(PurchasingRoutes.REQUISITIONS, "Solicitudes", "PLANEACIÓN",
                              "requisition_view", Icons.REQUEST, "requisitions"),
    PurchasingRouteDefinition(PurchasingRoutes.QUOTATIONS, "Cotizaciones", "COTIZACIONES",
                              "quotation_view", Icons.PRICE),
    PurchasingRouteDefinition(PurchasingRoutes.ORDERS, "Órdenes de compra", "ÓRDENES",
                              "order_view", Icons.ORDERS, "orders"),
    PurchasingRouteDefinition(PurchasingRoutes.DIRECT_PURCHASE_CREATE, "Nueva compra",
                              "COMPRA DIRECTA", "direct_create", Icons.ADD),
    PurchasingRouteDefinition(PurchasingRoutes.DIRECT_PURCHASE_HISTORY, "Historial",
                              "COMPRA DIRECTA", "direct_view", Icons.CLOCK, "direct_purchase"),
    PurchasingRouteDefinition(PurchasingRoutes.ORIGIN_LOADING, "Por cargar",
                              "COMPRA EN ORIGEN", "origin_view", Icons.PICKING),
    PurchasingRouteDefinition(PurchasingRoutes.RECEIPTS, "Pendientes y diferencias",
                              "RECEPCIONES", "receipt_view", Icons.RECEIVING),
    PurchasingRouteDefinition(PurchasingRoutes.INVOICES, "Facturas y conciliación",
                              "FACTURACIÓN", "invoice_view", Icons.DOCUMENT, "invoices"),
)

PURCHASING_GROUP_ICONS = {
    "COMPRAS": Icons.PURCHASES, "PLANEACIÓN": Icons.FORECAST, "COTIZACIONES": Icons.PRICE,
    "ÓRDENES": Icons.ORDERS, "COMPRA DIRECTA": Icons.ADD, "COMPRA EN ORIGEN": Icons.DELIVERY,
    "RECEPCIONES": Icons.RECEIVING, "FACTURACIÓN": Icons.DOCUMENT,
}


def visible_routes(capabilities) -> tuple[PurchasingRouteDefinition, ...]:
    """Return only implemented routes granted by the capability snapshot."""
    return tuple(route for route in IMPLEMENTED_PURCHASING_ROUTES
                 if bool(getattr(capabilities, route.capability, False)))
