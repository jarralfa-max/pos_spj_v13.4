"""ApplicationWindow + GlobalSidebar wiring — SHELL-12.

Additive to SHELL-11's `test_application_window.py`, which exercises
`ApplicationWindow` with `sidebar=None` (the default) and must keep
passing unmodified — these tests only cover the opt-in `sidebar` path.
"""
from PyQt5.QtWidgets import QLabel

from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from tests.ui.shell.conftest import make_context


def _routes() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="POS", view_factory_id="sales.pos_view",
    ))
    registry.register(RouteDefinition(
        route_id="inventory.overview", module_id="inventory", title="Inventario",
        view_factory_id="inventory.overview_view",
    ))
    return registry


def _view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: QLabel("POS"))
    registry.register("inventory.overview_view", lambda: QLabel("Inventario"))
    return registry


def _vm(item_id, route_id, label) -> SidebarItemViewModel:
    return SidebarItemViewModel(
        item_id=item_id, route_id=route_id, label=label, icon="sales",
        group="", order=0, badge_count=None, is_active=False,
    )


def _window_with_sidebar() -> tuple[ApplicationWindow, GlobalSidebar]:
    router = DesktopRouter(
        route_registry=_routes(), view_factory_registry=_view_factories(), initial_context=make_context(),
    )
    sidebar = GlobalSidebar()
    sidebar.set_items((
        _vm("nav.sales.pos", "sales.pos", "Punto de Venta"),
        _vm("nav.inventory.overview", "inventory.overview", "Inventario"),
    ))
    return ApplicationWindow(router=router, sidebar=sidebar), sidebar


def test_window_without_sidebar_still_works():
    router = DesktopRouter(
        route_registry=_routes(), view_factory_registry=_view_factories(), initial_context=make_context(),
    )
    win = ApplicationWindow(router=router)
    assert win.sidebar is None
    win.navigate("sales.pos")  # must not raise
    assert win.content_host.current_route_id == "sales.pos"


def test_sidebar_is_mounted_when_provided():
    win, sidebar = _window_with_sidebar()
    assert win.sidebar is sidebar


def test_clicking_sidebar_item_navigates_the_window():
    win, sidebar = _window_with_sidebar()
    sidebar._nav.setCurrentRow(1)
    assert win.content_host.current_route_id == "inventory.overview"


def test_navigating_the_window_highlights_the_matching_sidebar_row():
    win, sidebar = _window_with_sidebar()
    win.navigate("inventory.overview")
    assert sidebar._nav.currentRow() == 1


def test_navigating_via_window_does_not_trigger_a_second_navigation_from_the_sidebar():
    win, sidebar = _window_with_sidebar()
    calls = []
    original_navigate = win.navigate
    win.navigate = lambda route_id: calls.append(route_id) or original_navigate(route_id)
    win.navigate("inventory.overview")
    assert calls == ["inventory.overview"]
