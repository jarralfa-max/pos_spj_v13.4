"""Declarative navigation for the enterprise pricing/costing module (PRC-7).

Pure data: pages, Spanish titles/tooltips, icon keys, and the granular PRICING_*
permission each requires. The app shell renders this and hides an entry when the
session lacks the permission (hiding is UX, not security — the backend re-validates
every action). Declarative → testable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.pricing.permissions import PricingPermissions


@dataclass(frozen=True)
class NavEntry:
    page_id: str
    title: str        # es-MX
    icon: str
    permission: str
    tooltip: str


PRICING_NAV: tuple[NavEntry, ...] = (
    NavEntry("pricing_overview", "Resumen", "dashboard", PricingPermissions.VIEW,
             "Vista general: listas, precios, costos y precios bajo mínimo."),
    NavEntry("pricing_lists", "Listas de precio", "catalog", PricingPermissions.LIST_VIEW,
             "Listas base, de canal, de cliente y promocionales con su estado."),
    NavEntry("pricing_prices", "Precios por producto", "price",
             PricingPermissions.VIEW,
             "Precio de venta por producto, sucursal y lista; precio mínimo."),
    NavEntry("pricing_costs", "Costos", "cost", PricingPermissions.VIEW_COST,
             "Costo promedio, último y estándar por producto."),
    NavEntry("pricing_history", "Historial", "audit", PricingPermissions.VIEW_AUDIT,
             "Bitácora de cambios de precio y costo."),
    NavEntry("pricing_settings", "Configuración", "settings",
             PricingPermissions.SETTINGS_VIEW,
             "Parámetros del módulo de precios y costos."),
)


def visible_entries(has_permission) -> tuple[NavEntry, ...]:
    """Entries the session may see. ``has_permission(code) -> bool``."""
    return tuple(e for e in PRICING_NAV if has_permission(e.permission))
