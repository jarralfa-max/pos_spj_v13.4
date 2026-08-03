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


# §54 — navegación lateral (sidebar) del módulo de inventario enterprise. Cada
# sección es su propia página (ninguna ventana saturada): 21 secciones en el orden
# canónico del Design System SPJ. El shell oculta una entrada si la sesión no tiene
# su permiso granular (ocultar es UX; el backend revalida cada acción).
INVENTORY_NAV: tuple[NavEntry, ...] = (
    NavEntry("inventory_summary", "Resumen", "dashboard",
             InventoryPermissions.VIEW,
             "Vista general: existencias, alertas y reposición."),
    NavEntry("inventory_stock", "Existencias", "inventory",
             InventoryPermissions.VIEW,
             "Existencia física por producto, almacén y bucket."),
    NavEntry("inventory_availability", "Disponibilidad", "inventory",
             InventoryPermissions.VIEW,
             "Disponible para prometer (existencia − reservas) y desglose por bucket."),
    NavEntry("inventory_warehouses", "Almacenes", "warehouse",
             InventoryPermissions.WAREHOUSE_VIEW,
             "Almacenes por sucursal: tipo, estado y capacidades."),
    NavEntry("inventory_locations", "Ubicaciones", "location",
             InventoryPermissions.LOCATION_VIEW,
             "Zonas y ubicaciones jerárquicas (pasillo → rack → nivel → posición)."),
    NavEntry("inventory_lots", "Lotes", "lot",
             InventoryPermissions.LOT_VIEW,
             "Lotes, origen, estado de calidad y caducidad."),
    NavEntry("inventory_weight", "Peso variable", "scale",
             InventoryPermissions.WEIGHT_CAPTURE,
             "Captura de peso (catch weight) y báscula."),
    NavEntry("inventory_cold_chain", "Cadena de frío", "temperature",
             InventoryPermissions.TEMPERATURE_RECORD,
             "Lecturas de temperatura, excursiones y bloqueo automático."),
    NavEntry("inventory_reservations", "Reservas", "reservation",
             InventoryPermissions.RESERVATION_VIEW,
             "Reservas y asignaciones a lotes (FEFO)."),
    NavEntry("inventory_movements", "Movimientos", "movements",
             InventoryPermissions.MOVEMENT_VIEW,
             "Ledger de movimientos: entradas, salidas, transferencias."),
    NavEntry("inventory_transfers", "Transferencias", "transfer",
             InventoryPermissions.TRANSFER_VIEW,
             "Traslados entre almacenes con despacho y recepción."),
    NavEntry("inventory_receipts", "Recepciones", "receipt",
             InventoryPermissions.MOVEMENT_VIEW,
             "Recepciones de compra y producción hacia el inventario."),
    NavEntry("inventory_replenishment", "Reposición", "replenishment",
             InventoryPermissions.REPLENISHMENT_VIEW,
             "Sugerencias de compra y transferencia por reglas mín/máx."),
    NavEntry("inventory_counts", "Conteos", "count",
             InventoryPermissions.COUNT_VIEW,
             "Conteos cíclicos y físicos, reconteo y varianza."),
    NavEntry("inventory_adjustments", "Ajustes", "adjustment",
             InventoryPermissions.ADJUSTMENT_VIEW,
             "Ajustes con motivo, autorización y posteo."),
    NavEntry("inventory_quarantine", "Cuarentena", "quality",
             InventoryPermissions.QUARANTINE_VIEW,
             "Bloqueo, cuarentena y liberación de lotes."),
    NavEntry("inventory_expiry", "Caducidades", "calendar",
             InventoryPermissions.LOT_VIEW,
             "Riesgo de caducidad, alertas y barrido de vencidos."),
    NavEntry("inventory_traceability", "Trazabilidad", "traceability",
             InventoryPermissions.VIEW_TRACEABILITY,
             "Rastreo ascendente/descendente y reporte de recall."),
    NavEntry("inventory_alerts", "Alertas", "bell",
             InventoryPermissions.NOTIFICATIONS_MANAGE,
             "Reglas de notificación y alertas de WhatsApp."),
    NavEntry("inventory_audit", "Auditoría", "audit",
             InventoryPermissions.VIEW_AUDIT,
             "Bitácora de operaciones y autorizaciones de inventario."),
    NavEntry("inventory_settings", "Configuración", "settings",
             InventoryPermissions.SETTINGS_VIEW,
             "Parámetros del módulo: umbrales, políticas y catálogos."),
)


def visible_entries(has_permission) -> tuple[NavEntry, ...]:
    """Entries the session may see. ``has_permission(code) -> bool``."""
    return tuple(e for e in INVENTORY_NAV if has_permission(e.permission))
