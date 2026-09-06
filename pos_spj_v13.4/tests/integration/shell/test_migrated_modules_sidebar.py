"""SHELL-16½ piece 3 — the migrated modules' navigation items rendered
by the REAL `SidebarResolver` + `GlobalSidebar`, gated by a REAL
`ApplicationContext`'s permissions. Proves the whole chain (registry ->
resolver -> widget) is not just internally consistent on paper but
actually renders the right rows for a real permission set, and drops rows
whose module isn't registered in `ModuleRegistry` (a route can exist in
`RouteRegistry` without ever appearing here if its module was never
registered — this is exactly the ordering-independence the registries are
built to tolerate, exercised for real here).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.bootstrap.health.health_status import HealthReport, HealthStatus  # noqa: E402
from frontend.desktop.modules.business_intelligence.shell_registration import (
    build_business_intelligence_module_descriptor,
    build_business_intelligence_route_definition,
)
from frontend.desktop.modules.cash_register.shell_registration import (  # noqa: E402
    build_cash_register_module_descriptor, build_cash_register_route_definition,
)
from frontend.desktop.modules.configuracion.shell_registration import (
    build_configuracion_module_descriptor,
    build_configuracion_route_definition,
)
from frontend.desktop.modules.customers_crm.shell_registration import (  # noqa: E402
    build_customers_crm_module_descriptor, build_customers_crm_route_definition,
)
from frontend.desktop.modules.finance.shell_registration import (  # noqa: E402
    build_finance_module_descriptor, build_finance_route_definition,
)
from frontend.desktop.modules.hr.shell_registration import (  # noqa: E402
    build_hr_module_descriptor, build_hr_route_definition,
)
from frontend.desktop.modules.inventory.shell_registration import (  # noqa: E402
    build_inventory_module_descriptor, build_inventory_route_definition,
)
from frontend.desktop.modules.products.shell_registration import (  # noqa: E402
    build_products_module_descriptor, build_products_route_definition,
)
from frontend.desktop.modules.purchasing.shell_registration import (  # noqa: E402
    build_purchasing_module_descriptor, build_purchasing_route_definition,
)
from frontend.desktop.modules.sales_pos.shell_registration import (  # noqa: E402
    SALES_POS_REQUIRED_PERMISSION, SALES_POS_ROUTE_ID,
    build_sales_pos_module_descriptor, build_sales_pos_route_definition,
)
from frontend.desktop.modules.transfers.shell_registration import (  # noqa: E402
    TRANSFERS_ROUTE_ID, build_transfers_module_descriptor, build_transfers_route_definition,
)
from frontend.desktop.shell.modules.module_registry import ModuleRegistry  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar  # noqa: E402
from frontend.desktop.shell.sidebar.migrated_modules_navigation import (  # noqa: E402
    register_migrated_modules_navigation,
)
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry  # noqa: E402
from frontend.desktop.shell.sidebar.sidebar_resolver import SidebarResolver  # noqa: E402

_MODULE_BUILDERS = (
    (build_sales_pos_module_descriptor, build_sales_pos_route_definition),
    (build_customers_crm_module_descriptor, build_customers_crm_route_definition),
    (build_finance_module_descriptor, build_finance_route_definition),
    (build_hr_module_descriptor, build_hr_route_definition),
    (build_inventory_module_descriptor, build_inventory_route_definition),
    (build_products_module_descriptor, build_products_route_definition),
    (build_purchasing_module_descriptor, build_purchasing_route_definition),
    (build_transfers_module_descriptor, build_transfers_route_definition),
    (build_cash_register_module_descriptor, build_cash_register_route_definition),
    (build_configuracion_module_descriptor, build_configuracion_route_definition),
    (build_business_intelligence_module_descriptor, build_business_intelligence_route_definition),
)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _healthy_report() -> HealthReport:
    return HealthReport(overall_status=HealthStatus.HEALTHY, checks=(), generated_at=datetime.now(timezone.utc))


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Usuario", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire_all_migrated():
    modules = ModuleRegistry()
    routes = RouteRegistry()
    nav_items = NavigationItemRegistry()
    register_migrated_modules_navigation(nav_items)

    for build_module, build_route in _MODULE_BUILDERS:
        modules.register(build_module())
        routes.register(build_route())

    resolver = SidebarResolver(navigation_items=nav_items, route_registry=routes, module_registry=modules)
    return resolver, modules, routes


def test_all_migrated_items_resolve_when_every_permission_is_granted(app):
    resolver, _modules, _routes = _wire_all_migrated()
    context = _context(permissions={"*"})
    resolved = resolver.resolve(context=context, health_report=_healthy_report())
    assert len(resolved) == 11


def test_only_permitted_items_resolve_with_a_narrow_permission_set(app):
    resolver, _modules, _routes = _wire_all_migrated()
    context = _context(permissions={SALES_POS_REQUIRED_PERMISSION.upper()})
    resolved = resolver.resolve(context=context, health_report=_healthy_report())
    assert len(resolved) == 1
    assert resolved[0].route_id == SALES_POS_ROUTE_ID


def test_an_unregistered_module_drops_its_item_silently(app):
    # Only register transfers' route, never its module — SidebarResolver
    # must drop it rather than error, same as an unhealthy module would.
    modules = ModuleRegistry()
    routes = RouteRegistry()
    routes.register(build_transfers_route_definition())
    nav_items = NavigationItemRegistry()
    register_migrated_modules_navigation(nav_items)

    resolver = SidebarResolver(navigation_items=nav_items, route_registry=routes, module_registry=modules)
    resolved = resolver.resolve(context=_context(permissions={"*"}), health_report=_healthy_report())
    assert all(item.route_id != TRANSFERS_ROUTE_ID for item in resolved)


def test_global_sidebar_renders_the_resolved_items_as_real_rows(app):
    resolver, _modules, _routes = _wire_all_migrated()
    context = _context(permissions={"*"})
    resolved = resolver.resolve(context=context, health_report=_healthy_report())

    sidebar = GlobalSidebar()
    sidebar.set_items(resolved)
    assert sidebar.visible_item_count == 11
