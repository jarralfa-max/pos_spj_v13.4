"""SidebarResolver — SHELL-12.

Turns the full `NavigationItemRegistry` catalog into the filtered,
annotated list `GlobalSidebar` actually shows for the current
`ApplicationContext`: permission-gated (`PermissionEvaluator`, SHELL-6),
feature-flag-gated (`FeatureContext`, SHELL-6), and module-health-gated
(`ModuleHealthEvaluator`/`HealthReport`, SHELL-8) — the same three checks
`DesktopRouter._authorize()`/`_check_offline()` (SHELL-10) run before a
navigation, applied here to decide what's even worth showing as a link.

An item is dropped entirely — never shown disabled — if its `route_id`
isn't registered in `RouteRegistry`, its `module_id` isn't registered in
`ModuleRegistry`, or its module fails a health requirement: all three are
wiring problems, not something to present to the end user as a broken or
greyed-out menu entry. This matches `ModuleRegistry.usable_modules()`
(SHELL-8), which already established "unhealthy means absent," not "means
disabled" — SHELL-12 doesn't introduce a new visible-but-disabled state.
"""
from __future__ import annotations

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.health.health_status import HealthReport
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from frontend.desktop.shell.modules.health_requirement import ModuleHealthEvaluator
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.sidebar.badge_registry import BadgeRegistry
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel


class SidebarResolver:
    def __init__(
        self,
        *,
        navigation_items: NavigationItemRegistry,
        route_registry: RouteRegistry,
        module_registry: ModuleRegistry,
        badge_registry: BadgeRegistry | None = None,
        health_evaluator: ModuleHealthEvaluator | None = None,
    ) -> None:
        self._items = navigation_items
        self._routes = route_registry
        self._modules = module_registry
        self._badges = badge_registry or BadgeRegistry()
        self._health_evaluator = health_evaluator or ModuleHealthEvaluator()

    def resolve(
        self, *, context: ApplicationContext, health_report: HealthReport,
        current_route_id: str | None = None,
    ) -> tuple[SidebarItemViewModel, ...]:
        evaluator = PermissionEvaluator(context)
        resolved: list[SidebarItemViewModel] = []
        for item in self._items.all():
            if not self._routes.is_registered(item.route_id):
                continue
            module = self._modules.get(item.module_id)
            if module is None:
                continue
            if not self._health_evaluator.is_satisfied(module.health_requirements, health_report):
                continue
            if item.required_permission and not evaluator.has_permission(item.required_permission):
                continue
            if item.feature_flag and not context.feature_context.is_enabled(item.feature_flag):
                continue
            resolved.append(SidebarItemViewModel(
                item_id=item.item_id, route_id=item.route_id, label=item.label, icon=item.icon,
                group=item.group, order=item.order,
                badge_count=self._badges.count_for(item.badge_key) if item.badge_key else None,
                is_active=(item.route_id == current_route_id),
            ))
        return tuple(resolved)

    def active_item_id_for_route(self, route_id: str | None) -> str | None:
        if route_id is None:
            return None
        item = self._items.item_for_route(route_id)
        return item.item_id if item is not None else None
