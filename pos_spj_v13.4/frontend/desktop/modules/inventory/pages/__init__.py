"""Enterprise inventory pages (PyQt5, presentation-only). INV-25."""

from frontend.desktop.modules.inventory.pages.analytics_page import (
    InventoryAnalyticsPage,
)
from frontend.desktop.modules.inventory.pages.availability_page import AvailabilityPage
from frontend.desktop.modules.inventory.pages.expiry_page import ExpiryPage
from frontend.desktop.modules.inventory.pages.inventory_dashboard_page import (
    InventoryDashboardPage,
)
from frontend.desktop.modules.inventory.pages.locations_page import LocationsPage
from frontend.desktop.modules.inventory.pages.lots_page import LotsPage
from frontend.desktop.modules.inventory.pages.movements_page import MovementsPage
from frontend.desktop.modules.inventory.pages.placeholder_page import PlaceholderPage
from frontend.desktop.modules.inventory.pages.quarantine_page import QuarantinePage
from frontend.desktop.modules.inventory.pages.replenishment_page import (
    ReplenishmentPage,
)
from frontend.desktop.modules.inventory.pages.reservations_page import (
    ReservationsPage,
)
from frontend.desktop.modules.inventory.pages.stock_page import StockPage
from frontend.desktop.modules.inventory.pages.traceability_page import (
    TraceabilityPage,
)
from frontend.desktop.modules.inventory.pages.warehouses_page import WarehousesPage

__all__ = [
    "AvailabilityPage",
    "ExpiryPage",
    "InventoryAnalyticsPage",
    "InventoryDashboardPage",
    "LocationsPage",
    "LotsPage",
    "MovementsPage",
    "PlaceholderPage",
    "QuarantinePage",
    "ReplenishmentPage",
    "ReservationsPage",
    "StockPage",
    "TraceabilityPage",
    "WarehousesPage",
]
