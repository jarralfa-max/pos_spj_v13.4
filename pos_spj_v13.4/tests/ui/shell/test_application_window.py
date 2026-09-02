from PyQt5.QtWidgets import QLabel

from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.ui.shell.conftest import make_context


def _routes() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="POS", view_factory_id="sales.pos_view",
        breadcrumb=("Ventas", "Punto de Venta"), cache_policy=CachePolicy.KEEP_ALIVE,
    ))
    registry.register(RouteDefinition(
        route_id="inventory.overview", module_id="inventory", title="Inventario",
        view_factory_id="inventory.overview_view", breadcrumb=("Inventario",),
    ))
    return registry


def _view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: QLabel("POS"))
    registry.register("inventory.overview_view", lambda: QLabel("Inventario"))
    return registry


def _window(context=None) -> ApplicationWindow:
    router = DesktopRouter(
        route_registry=_routes(), view_factory_registry=_view_factories(),
        initial_context=context or make_context(),
    )
    return ApplicationWindow(router=router)


def test_construction_applies_initial_context_to_chrome():
    ctx = make_context(branch_name="Sucursal Centro", user_name="Jose Alfaro")
    win = _window(ctx)
    assert "Sucursal Centro" in win.top_bar.context_text
    assert "Jose Alfaro" in win.top_bar.context_text
    assert "Sucursal Centro" in win.status_bar.workstation_text


def test_navigate_updates_content_host_and_breadcrumb():
    win = _window()
    win.navigate("sales.pos")
    assert win.content_host.current_route_id == "sales.pos"
    assert win.top_bar.breadcrumb_text == "Ventas › Punto de Venta"


def test_navigate_marks_degraded_offline_in_status_bar():
    # sales.pos/inventory.overview have no offline_policy override (defaults
    # to REQUIRES_ONLINE), so build a route whose policy actually permits
    # degraded offline use.
    from frontend.desktop.shell.routing.offline_policy import OfflinePolicy

    routes = RouteRegistry()
    routes.register(RouteDefinition(
        route_id="reports.dashboard", module_id="reports", title="Dashboard",
        view_factory_id="v", offline_policy=OfflinePolicy.DEGRADED_OFFLINE,
    ))
    vf = ViewFactoryRegistry()
    vf.register("v", lambda: QLabel("Dashboard"))
    ctx = make_context(offline_status="OFFLINE")
    router = DesktopRouter(route_registry=routes, view_factory_registry=vf, initial_context=ctx)
    win = ApplicationWindow(router=router)
    win.navigate("reports.dashboard")
    assert win.status_bar.connectivity_text == "Conexión limitada"


def test_go_back_and_go_forward_update_content_host():
    win = _window()
    win.navigate("sales.pos")
    win.navigate("inventory.overview")
    win.go_back()
    assert win.content_host.current_route_id == "sales.pos"
    win.go_forward()
    assert win.content_host.current_route_id == "inventory.overview"


def test_keep_alive_route_view_persists_across_navigation():
    win = _window()
    win.navigate("sales.pos")
    first_widget = win.content_host._stack.currentWidget()
    win.navigate("inventory.overview")
    win.navigate("sales.pos")
    assert win.content_host._stack.currentWidget() is first_widget


def test_notifications_toggle_button_opens_and_closes_drawer():
    win = _window()
    assert win.notification_drawer.is_open is False
    win.top_bar._notifications_button.click()
    assert win.notification_drawer.is_open is True
    win.top_bar._notifications_button.click()
    assert win.notification_drawer.is_open is False


def test_adding_notification_updates_top_bar_unread_count():
    from datetime import datetime, timezone

    from frontend.desktop.shell.application_shell.notification_drawer import NotificationItem

    win = _window()
    win.notification_drawer.add_notification(
        NotificationItem("n1", "Título", "Mensaje", datetime.now(timezone.utc))
    )
    assert win.top_bar.unread_notification_count == 1


def test_update_context_refreshes_top_bar_and_status_bar():
    win = _window(make_context(branch_name="Sucursal Centro"))
    new_ctx = win.router.current_context.with_branch(
        branch_id="branch-2", branch_name="Sucursal Norte",
        permissions=win.router.current_context.permissions,
        feature_context=win.router.current_context.feature_context,
    )
    win.update_context(new_ctx)
    assert "Sucursal Norte" in win.top_bar.context_text
    assert "Sucursal Norte" in win.status_bar.workstation_text


def test_update_context_evicts_recreate_on_context_change_cache():
    routes = RouteRegistry()
    from frontend.desktop.shell.routing.offline_policy import OfflinePolicy  # noqa: F401
    routes.register(RouteDefinition(
        route_id="reports.dashboard", module_id="reports", title="Dashboard",
        view_factory_id="v", cache_policy=CachePolicy.RECREATE_ON_CONTEXT_CHANGE,
    ))
    vf = ViewFactoryRegistry()
    vf.register("v", lambda: QLabel("dashboard"))
    ctx = make_context()
    router = DesktopRouter(route_registry=routes, view_factory_registry=vf, initial_context=ctx)
    win = ApplicationWindow(router=router)
    win.navigate("reports.dashboard")
    first_widget = win.content_host._stack.currentWidget()

    win.update_context(ctx.with_branch(
        branch_id="branch-2", branch_name="Sucursal Norte",
        permissions=ctx.permissions, feature_context=ctx.feature_context,
    ))
    win.navigate("reports.dashboard")
    second_widget = win.content_host._stack.currentWidget()
    assert first_widget is not second_widget
