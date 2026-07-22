"""Enterprise inventory pages (PyQt5, presentation-only). INV-25."""

from frontend.desktop.modules.inventory.pages.inventory_dashboard_page import (
    InventoryDashboardPage,
)
from frontend.desktop.modules.inventory.pages.locations_page import LocationsPage
from frontend.desktop.modules.inventory.pages.replenishment_page import (
    ReplenishmentPage,
)
from frontend.desktop.modules.inventory.pages.warehouses_page import WarehousesPage

__all__ = [
    "InventoryDashboardPage",
    "LocationsPage",
    "ReplenishmentPage",
    "WarehousesPage",
]
