"""Page registry (§54) — maps each sidebar section to its page factory.

Given the canonical ``INVENTORY_NAV`` (21 sections), this returns the ordered
list of ``(factory, title)`` the ``InventoryView`` shell renders. Sections with a
built enterprise page use it; the rest fall back to a DS ``PlaceholderPage`` so the
sidebar is complete from day one without a saturated catch-all window. Pure
wiring — no Qt widgets are constructed here (factories run lazily in the shell).
"""

from __future__ import annotations

from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV
from frontend.desktop.modules.inventory.pages import (
    AvailabilityPage,
    ExpiryPage,
    InventoryDashboardPage,
    LocationsPage,
    LotsPage,
    MovementsPage,
    PlaceholderPage,
    ReplenishmentPage,
    StockPage,
    TraceabilityPage,
    WarehousesPage,
)

# page_id -> factory(presenter) -> QWidget. Sólo secciones con página real.
_REAL_PAGES = {
    "inventory_summary": InventoryDashboardPage,
    "inventory_stock": StockPage,
    "inventory_availability": AvailabilityPage,
    "inventory_warehouses": WarehousesPage,
    "inventory_locations": LocationsPage,
    "inventory_lots": LotsPage,
    "inventory_movements": MovementsPage,
    "inventory_expiry": ExpiryPage,
    "inventory_traceability": TraceabilityPage,
    "inventory_replenishment": ReplenishmentPage,
}


def _placeholder_factory(entry):
    def factory(_presenter):
        return PlaceholderPage(title=entry.title, subtitle=entry.tooltip)
    return factory


def build_page_specs():
    """Ordered ``[(factory, title)]`` for the 21 canonical sidebar sections.

    ``factory(presenter) -> QWidget``. Built pages get their real factory; the
    rest get a ``PlaceholderPage`` carrying the section's title/tooltip."""
    specs = []
    for entry in INVENTORY_NAV:
        real = _REAL_PAGES.get(entry.page_id)
        factory = real if real is not None else _placeholder_factory(entry)
        specs.append((factory, entry.title))
    return specs
