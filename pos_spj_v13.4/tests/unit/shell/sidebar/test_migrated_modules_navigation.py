"""SHELL-16½ piece 3 — the 9 migrated modules' real `NavigationItemDefinition`s.

Every prior `NavigationItemDefinition` in the test suite used fictional
ids; these are built from each module's own real `shell_registration.py`
constants. This file guards against the ids drifting apart by construction
error (a typo here would silently produce a sidebar entry that resolves to
nothing at `SidebarResolver` time, never a loud failure).
"""
from __future__ import annotations

from frontend.desktop.modules.cash_register.shell_registration import (
    CASH_REGISTER_MODULE_ID, CASH_REGISTER_REQUIRED_PERMISSION, CASH_REGISTER_ROUTE_ID,
)
from frontend.desktop.modules.customers_crm.shell_registration import (
    CUSTOMERS_CRM_MODULE_ID, CUSTOMERS_CRM_REQUIRED_PERMISSION, CUSTOMERS_CRM_ROUTE_ID,
)
from frontend.desktop.modules.finance.shell_registration import (
    FINANCE_MODULE_ID, FINANCE_REQUIRED_PERMISSION, FINANCE_ROUTE_ID,
)
from frontend.desktop.modules.hr.shell_registration import HR_MODULE_ID, HR_REQUIRED_PERMISSION, HR_ROUTE_ID
from frontend.desktop.modules.inventory.shell_registration import (
    INVENTORY_MODULE_ID, INVENTORY_REQUIRED_PERMISSION, INVENTORY_ROUTE_ID,
)
from frontend.desktop.modules.products.shell_registration import (
    PRODUCTS_MODULE_ID, PRODUCTS_REQUIRED_PERMISSION, PRODUCTS_ROUTE_ID,
)
from frontend.desktop.modules.purchasing.shell_registration import (
    PURCHASING_MODULE_ID, PURCHASING_REQUIRED_PERMISSION, PURCHASING_ROUTE_ID,
)
from frontend.desktop.modules.sales_pos.shell_registration import (
    SALES_POS_MODULE_ID, SALES_POS_REQUIRED_PERMISSION, SALES_POS_ROUTE_ID,
)
from frontend.desktop.modules.transfers.shell_registration import (
    TRANSFERS_MODULE_ID, TRANSFERS_REQUIRED_PERMISSION, TRANSFERS_ROUTE_ID,
)
from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
    MIGRATED_MODULES_NAVIGATION_ITEMS,
    register_migrated_modules_navigation,
)
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry

_EXPECTED = {
    SALES_POS_MODULE_ID: (SALES_POS_ROUTE_ID, SALES_POS_REQUIRED_PERMISSION),
    CASH_REGISTER_MODULE_ID: (CASH_REGISTER_ROUTE_ID, CASH_REGISTER_REQUIRED_PERMISSION),
    INVENTORY_MODULE_ID: (INVENTORY_ROUTE_ID, INVENTORY_REQUIRED_PERMISSION),
    TRANSFERS_MODULE_ID: (TRANSFERS_ROUTE_ID, TRANSFERS_REQUIRED_PERMISSION),
    PRODUCTS_MODULE_ID: (PRODUCTS_ROUTE_ID, PRODUCTS_REQUIRED_PERMISSION),
    CUSTOMERS_CRM_MODULE_ID: (CUSTOMERS_CRM_ROUTE_ID, CUSTOMERS_CRM_REQUIRED_PERMISSION),
    PURCHASING_MODULE_ID: (PURCHASING_ROUTE_ID, PURCHASING_REQUIRED_PERMISSION),
    FINANCE_MODULE_ID: (FINANCE_ROUTE_ID, FINANCE_REQUIRED_PERMISSION),
    HR_MODULE_ID: (HR_ROUTE_ID, HR_REQUIRED_PERMISSION),
}


def test_exactly_nine_items_one_per_migrated_module():
    assert len(MIGRATED_MODULES_NAVIGATION_ITEMS) == 9
    assert {item.module_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS} == set(_EXPECTED)


def test_every_item_matches_its_modules_real_route_and_permission():
    for item in MIGRATED_MODULES_NAVIGATION_ITEMS:
        expected_route, expected_permission = _EXPECTED[item.module_id]
        assert item.route_id == expected_route
        assert item.required_permission == expected_permission


def test_item_ids_are_unique():
    ids = [item.item_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS]
    assert len(ids) == len(set(ids))


def test_orders_are_unique_so_render_sequence_is_deterministic():
    orders = [item.order for item in MIGRATED_MODULES_NAVIGATION_ITEMS]
    assert len(orders) == len(set(orders))


def test_register_all_populates_a_real_registry_without_duplicates():
    registry = NavigationItemRegistry()
    register_migrated_modules_navigation(registry)
    assert len(registry.all()) == 9
    for module_id, (route_id, _permission) in _EXPECTED.items():
        item = registry.item_for_route(route_id)
        assert item is not None
        assert item.module_id == module_id
