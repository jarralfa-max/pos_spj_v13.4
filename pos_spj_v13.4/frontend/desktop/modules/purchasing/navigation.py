"""Canonical, permission-aware information architecture for desktop Purchasing."""

from __future__ import annotations

from dataclasses import dataclass


class PurchasingRoutes:
    DASHBOARD = "dashboard"
    REQUISITIONS = "requisitions"
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
    badge_key: str | None = None


IMPLEMENTED_PURCHASING_ROUTES = (
    PurchasingRouteDefinition(PurchasingRoutes.DASHBOARD, "Resumen", "COMPRAS",
                              "module_view"),
    PurchasingRouteDefinition(PurchasingRoutes.REQUISITIONS, "Solicitudes", "PLANEACIÓN",
                              "requisition_view", "requisitions"),
    PurchasingRouteDefinition(PurchasingRoutes.ORDERS, "Órdenes de compra", "ÓRDENES",
                              "order_view", "orders"),
    PurchasingRouteDefinition(PurchasingRoutes.DIRECT_PURCHASE_CREATE, "Nueva compra",
                              "COMPRA DIRECTA", "direct_create"),
    PurchasingRouteDefinition(PurchasingRoutes.DIRECT_PURCHASE_HISTORY, "Historial",
                              "COMPRA DIRECTA", "direct_view", "direct_purchase"),
    PurchasingRouteDefinition(PurchasingRoutes.ORIGIN_LOADING, "Por cargar",
                              "COMPRA EN ORIGEN", "origin_view"),
    PurchasingRouteDefinition(PurchasingRoutes.RECEIPTS, "Pendientes y diferencias",
                              "RECEPCIONES", "receipt_view"),
    PurchasingRouteDefinition(PurchasingRoutes.INVOICES, "Facturas y conciliación",
                              "FACTURACIÓN", "invoice_view", "invoices"),
)


def visible_routes(capabilities) -> tuple[PurchasingRouteDefinition, ...]:
    """Return only implemented routes granted by the capability snapshot."""
    return tuple(route for route in IMPLEMENTED_PURCHASING_ROUTES
                 if bool(getattr(capabilities, route.capability, False)))
