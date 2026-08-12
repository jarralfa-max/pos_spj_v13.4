"""Enterprise inventory desktop module (INV-25).

Presentation split: ``view_models`` (pure mappers + es-MX labels), ``presenter``
(bridge to backend query services / use cases), ``navigation`` (declarative page
map + granular permissions), and ``pages`` (PyQt5, presentation-only). No SQL,
no business logic in the UI.
"""

from frontend.desktop.modules.inventory.capability_resolver import (
    resolve_inventory_capabilities,
)
from frontend.desktop.modules.inventory.navigation import (
    INVENTORY_NAV,
    NavEntry,
    visible_entries,
)
from frontend.desktop.modules.inventory.presenter import InventoryPresenter
from frontend.desktop.modules.inventory.view_models import InventoryCapabilities

__all__ = [
    "INVENTORY_NAV",
    "InventoryCapabilities",
    "InventoryPresenter",
    "NavEntry",
    "resolve_inventory_capabilities",
    "visible_entries",
]
