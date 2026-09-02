"""ApplicationWindow + ModuleLoader wiring — SHELL-13.

Additive to SHELL-11's `test_application_window.py`, which exercises
`ApplicationWindow` with `module_loader=None` (the default) and must keep
passing unmodified — these tests only cover the opt-in `module_loader`
path.
"""
from PyQt5.QtWidgets import QLabel

from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState
from frontend.desktop.shell.loading.module_loader import ModuleLoader
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.ui.shell.conftest import make_context
from tests.unit.shell.loading.conftest import RecordingActivator


def _modules() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(ModuleDescriptor(module_id="sales", display_name="Ventas", startup_mode=StartupMode.EAGER))
    registry.register(ModuleDescriptor(module_id="broken", display_name="Roto", startup_mode=StartupMode.LAZY))
    return registry


def _routes() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="POS", view_factory_id="sales.pos_view",
    ))
    registry.register(RouteDefinition(
        route_id="broken.page", module_id="broken", title="Roto", view_factory_id="broken.page_view",
        breadcrumb=("Roto",),
    ))
    return registry


def _view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: QLabel("POS"))
    registry.register("broken.page_view", lambda: QLabel("Roto"))
    return registry


def _window(activator) -> tuple[ApplicationWindow, ModuleLoader, DesktopRouter]:
    router = DesktopRouter(
        route_registry=_routes(), view_factory_registry=_view_factories(), initial_context=make_context(),
    )
    loader = ModuleLoader(module_registry=_modules(), activator=activator)
    return ApplicationWindow(router=router, module_loader=loader), loader, router


def test_eager_module_is_activated_at_construction():
    activator = RecordingActivator()
    _window(activator)
    assert "sales" in activator.calls


def test_window_without_module_loader_still_works():
    router = DesktopRouter(
        route_registry=_routes(), view_factory_registry=_view_factories(), initial_context=make_context(),
    )
    win = ApplicationWindow(router=router)
    win.navigate("sales.pos")  # must not raise
    assert win.content_host.current_route_id == "sales.pos"


def test_navigating_to_a_lazy_module_activates_it_on_first_navigation():
    activator = RecordingActivator()
    win, loader, router = _window(activator)
    assert loader.is_loaded("broken") is False
    win.navigate("broken.page")
    assert loader.is_loaded("broken") is True


def test_navigating_to_a_module_that_fails_to_load_shows_an_error_view():
    activator = RecordingActivator()
    activator.fail_for.add("broken")
    win, loader, router = _window(activator)
    result = win.navigate("broken.page")
    assert result.load_failed is True
    assert win.content_host.current_route_id == "broken.page"


def test_failed_load_does_not_advance_router_history():
    activator = RecordingActivator()
    activator.fail_for.add("broken")
    win, loader, router = _window(activator)
    win.navigate("broken.page")
    assert router.current_route_id is None


def test_failed_load_still_updates_breadcrumb_to_the_attempted_route():
    activator = RecordingActivator()
    activator.fail_for.add("broken")
    win, loader, router = _window(activator)
    win.navigate("broken.page")
    assert win.top_bar.breadcrumb_text == "Roto"


def test_retrying_after_activation_recovers_succeeds():
    activator = RecordingActivator()
    activator.fail_for.add("broken")
    win, loader, router = _window(activator)
    first = win.navigate("broken.page")
    assert first.load_failed is True

    activator.fail_for.discard("broken")
    second = win.navigate("broken.page")
    assert second.load_failed is False
    assert router.current_route_id == "broken.page"
    assert win.content_host.current_route_id == "broken.page"


def test_error_view_retry_button_re_navigates():
    activator = RecordingActivator()
    activator.fail_for.add("broken")
    win, loader, router = _window(activator)
    result = win.navigate("broken.page")

    activator.fail_for.discard("broken")
    result.view.retry_button.click()
    assert router.current_route_id == "broken.page"
    assert win.content_host.current_route_id == "broken.page"


def test_background_preload_module_is_loaded_with_default_synchronous_scheduler():
    activator = RecordingActivator()
    modules = ModuleRegistry()
    modules.register(ModuleDescriptor(
        module_id="reports", display_name="Reportes", startup_mode=StartupMode.BACKGROUND_PRELOAD,
    ))
    router = DesktopRouter(
        route_registry=RouteRegistry(), view_factory_registry=ViewFactoryRegistry(),
        initial_context=make_context(),
    )
    loader = ModuleLoader(module_registry=modules, activator=activator)
    ApplicationWindow(router=router, module_loader=loader)
    assert loader.is_loaded("reports") is True
