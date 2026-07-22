"""Declarative navigation for the enterprise inventory module (§46, §54).

Pure data: the pages, their Spanish titles/tooltips, icon keys and the granular
INVENTORY_* permission each requires. The app shell renders this and hides an
entry when the session lacks the permission (hiding is UX, not security — the
backend re-validates every action). Keeping this declarative makes the module
map testable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.inventory.permissions import InventoryPermissions


@dataclass(frozen=True)
class NavEntry:
    page_id: str
    title: str        # es-MX
    icon: str
    permission: str
    tooltip: str


INVENTORY_NAV: tuple[NavEntry, ...] = (
    NavEntry("inventory_dashboard", "Panel de Inventario", "dashboard",
             InventoryPermissions.VIEW,
             "Vista general: existencias, alertas y reposición."),
    NavEntry("inventory_warehouses", "Almacenes", "warehouse",
             InventoryPermissions.WAREHOUSE_VIEW,
             "Almacenes por sucursal: tipo, estado y capacidades."),
    NavEntry("inventory_locations", "Ubicaciones", "location",
             InventoryPermissions.LOCATION_VIEW,
             "Zonas y ubicaciones jerárquicas (pasillo → rack → nivel → posición)."),
    NavEntry("inventory_availability", "Disponibilidad", "inventory",
             InventoryPermissions.VIEW,
             "Existencia disponible por producto, sucursal y almacén."),
    NavEntry("inventory_movements", "Movimientos", "movements",
             InventoryPermissions.MOVEMENT_VIEW,
             "Ledger de movimientos: entradas, salidas, transferencias."),
    NavEntry("inventory_replenishment", "Reposición", "replenishment",
             InventoryPermissions.REPLENISHMENT_VIEW,
             "Sugerencias de compra y transferencia por reglas mín/máx."),
    NavEntry("inventory_counts", "Conteos", "count",
             InventoryPermissions.COUNT_VIEW,
             "Conteos cíclicos y físicos, reconteo y varianza."),
    NavEntry("inventory_adjustments", "Ajustes", "adjustment",
             InventoryPermissions.ADJUSTMENT_VIEW,
             "Ajustes con motivo, autorización y posteo."),
    NavEntry("inventory_transfers", "Transferencias", "transfer",
             InventoryPermissions.TRANSFER_VIEW,
             "Traslados entre almacenes con despacho y recepción."),
    NavEntry("inventory_quality", "Calidad y cuarentena", "quality",
             InventoryPermissions.QUARANTINE_VIEW,
             "Bloqueo, cuarentena y liberación de lotes."),
    NavEntry("inventory_traceability", "Trazabilidad", "traceability",
             InventoryPermissions.VIEW_TRACEABILITY,
             "Rastreo ascendente/descendente y reporte de recall."),
    NavEntry("inventory_notifications", "Alertas", "bell",
             InventoryPermissions.NOTIFICATIONS_MANAGE,
             "Reglas de notificación y alertas de WhatsApp."),
    NavEntry("inventory_analytics", "Analítica", "chart",
             InventoryPermissions.EXPORT,
             "KPIs, gráficos de existencias/movimientos/merma y exportación."),
)


def visible_entries(has_permission) -> tuple[NavEntry, ...]:
    """Entries the session may see. ``has_permission(code) -> bool``."""
    return tuple(e for e in INVENTORY_NAV if has_permission(e.permission))
