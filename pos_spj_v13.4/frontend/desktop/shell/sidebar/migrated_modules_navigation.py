"""Real `NavigationItemDefinition`s for the SHELL-16-migrated modules —
SHELL-16½ (new-shell live-wiring prerequisite, piece 3 of 4).

Every existing `NavigationItemDefinition` construction anywhere in the
repo, before this file, was a fictional 1-item test fixture (`item_id=
"nav.sales.pos"`, `module_id="sales"`, ids that don't match any real
module). None of the 9 migrated modules' `shell_registration.py` files
populate `ModuleDescriptor.navigation_items` either — `GlobalSidebar` has
never had anything real to render for them. This file is that: one
`NavigationItemDefinition` per migrated module, built from each module's
own real, already-existing `MODULE_ID`/`ROUTE_ID`/`..._REQUIRED_PERMISSION`
constants (never re-typed by hand — a typo here would silently produce a
sidebar item that resolves to nothing, since `SidebarResolver` drops
unregistered `route_id`/`module_id` items rather than erroring).

Labels match `interfaz/menu_lateral.py`'s existing Spanish button text
verbatim (minus the emoji prefix — new-shell icons are semantic
identifiers, not emoji; see `test_no_emoji_icons_in_new_frontend`), so a
user moving from the legacy menu to this one sees the same names. `order`
follows the same top-to-bottom sequence `menu_lateral.py` already uses for
these 9 buttons.

Not itself wired into `NavigationItemRegistry` here — `register_migrated_
modules_navigation()` is a small helper for whatever composes the real
shell (main.py's eventual replacement) to call once, matching how
`ModuleRegistry`/`RouteRegistry` are populated by that same caller, not by
this module importing and mutating a registry at import time.
"""
from __future__ import annotations

from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.business_intelligence.shell_registration import (
    BUSINESS_INTELLIGENCE_MODULE_ID,
    BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION,
    BUSINESS_INTELLIGENCE_ROUTE_ID,
)
from frontend.desktop.modules.cash_register.shell_registration import (
    CASH_REGISTER_MODULE_ID,
    CASH_REGISTER_REQUIRED_PERMISSION,
    CASH_REGISTER_ROUTE_ID,
)
from frontend.desktop.modules.configuracion.shell_registration import (
    CONFIGURACION_MODULE_ID,
    CONFIGURACION_REQUIRED_PERMISSION,
    CONFIGURACION_ROUTE_ID,
)
from frontend.desktop.modules.customers_crm.shell_registration import (
    CUSTOMERS_CRM_MODULE_ID,
    CUSTOMERS_CRM_REQUIRED_PERMISSION,
    CUSTOMERS_CRM_ROUTE_ID,
)
from frontend.desktop.modules.finance.shell_registration import (
    FINANCE_MODULE_ID,
    FINANCE_REQUIRED_PERMISSION,
    FINANCE_ROUTE_ID,
)
from frontend.desktop.modules.hr.shell_registration import (
    HR_MODULE_ID,
    HR_REQUIRED_PERMISSION,
    HR_ROUTE_ID,
)
from frontend.desktop.modules.inventory.shell_registration import (
    INVENTORY_MODULE_ID,
    INVENTORY_REQUIRED_PERMISSION,
    INVENTORY_ROUTE_ID,
)
from frontend.desktop.modules.products.shell_registration import (
    PRODUCTS_MODULE_ID,
    PRODUCTS_REQUIRED_PERMISSION,
    PRODUCTS_ROUTE_ID,
)
from frontend.desktop.modules.purchasing.shell_registration import (
    PURCHASING_MODULE_ID,
    PURCHASING_REQUIRED_PERMISSION,
    PURCHASING_ROUTE_ID,
)
from frontend.desktop.modules.sales_pos.shell_registration import (
    SALES_POS_MODULE_ID,
    SALES_POS_REQUIRED_PERMISSION,
    SALES_POS_ROUTE_ID,
)
from frontend.desktop.modules.transfers.shell_registration import (
    TRANSFERS_MODULE_ID,
    TRANSFERS_REQUIRED_PERMISSION,
    TRANSFERS_ROUTE_ID,
)
from frontend.desktop.shell.sidebar.navigation_item_definition import NavigationItemDefinition
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry

MIGRATED_MODULES_GROUP = "operacion"

MIGRATED_MODULES_NAVIGATION_ITEMS: tuple[NavigationItemDefinition, ...] = (
    NavigationItemDefinition(
        item_id="nav.sales_pos", module_id=SALES_POS_MODULE_ID, route_id=SALES_POS_ROUTE_ID,
        label="Punto de Venta", icon=Icons.SALES, order=10, group=MIGRATED_MODULES_GROUP,
        required_permission=SALES_POS_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.cash_register", module_id=CASH_REGISTER_MODULE_ID, route_id=CASH_REGISTER_ROUTE_ID,
        label="Caja / Cortes Z", icon=Icons.CASH, order=20, group=MIGRATED_MODULES_GROUP,
        required_permission=CASH_REGISTER_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.inventory", module_id=INVENTORY_MODULE_ID, route_id=INVENTORY_ROUTE_ID,
        label="Inventario", icon=Icons.INVENTORY, order=30, group=MIGRATED_MODULES_GROUP,
        required_permission=INVENTORY_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.transfers", module_id=TRANSFERS_MODULE_ID, route_id=TRANSFERS_ROUTE_ID,
        label="Transferencias", icon=Icons.TRANSFERS, order=40, group=MIGRATED_MODULES_GROUP,
        required_permission=TRANSFERS_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.products", module_id=PRODUCTS_MODULE_ID, route_id=PRODUCTS_ROUTE_ID,
        label="Productos", icon=Icons.PRODUCTS, order=50, group=MIGRATED_MODULES_GROUP,
        required_permission=PRODUCTS_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.customers_crm", module_id=CUSTOMERS_CRM_MODULE_ID, route_id=CUSTOMERS_CRM_ROUTE_ID,
        label="Clientes y CRM", icon=Icons.CUSTOMERS, order=60, group=MIGRATED_MODULES_GROUP,
        required_permission=CUSTOMERS_CRM_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.purchasing", module_id=PURCHASING_MODULE_ID, route_id=PURCHASING_ROUTE_ID,
        label="Compras", icon=Icons.PURCHASES, order=70, group=MIGRATED_MODULES_GROUP,
        required_permission=PURCHASING_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.finance", module_id=FINANCE_MODULE_ID, route_id=FINANCE_ROUTE_ID,
        label="Finanzas", icon=Icons.FINANCE, order=80, group=MIGRATED_MODULES_GROUP,
        required_permission=FINANCE_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.hr", module_id=HR_MODULE_ID, route_id=HR_ROUTE_ID,
        label="Recursos Humanos", icon=Icons.HR, order=90, group=MIGRATED_MODULES_GROUP,
        required_permission=HR_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.configuracion", module_id=CONFIGURACION_MODULE_ID, route_id=CONFIGURACION_ROUTE_ID,
        label="Configuración", icon=Icons.SETTINGS, order=100, group=MIGRATED_MODULES_GROUP,
        required_permission=CONFIGURACION_REQUIRED_PERMISSION,
    ),
    NavigationItemDefinition(
        item_id="nav.business_intelligence", module_id=BUSINESS_INTELLIGENCE_MODULE_ID,
        route_id=BUSINESS_INTELLIGENCE_ROUTE_ID, label="Inteligencia de Negocios",
        icon=Icons.ANALYTICS, order=110, group=MIGRATED_MODULES_GROUP,
        required_permission=BUSINESS_INTELLIGENCE_REQUIRED_PERMISSION,
    ),
)


def register_migrated_modules_navigation(registry: NavigationItemRegistry) -> None:
    """Register every migrated module's nav item into `registry`. Called
    once by whatever composes the real shell — this module has no import-
    time side effects of its own."""
    for item in MIGRATED_MODULES_NAVIGATION_ITEMS:
        registry.register(item)
