"""ApplicationWindow + BackgroundServiceSupervisor wiring — SHELL-14.

Additive to SHELL-11's `test_application_window.py`, which exercises
`ApplicationWindow` with `service_supervisor=None` (the default) and must
keep passing unmodified — these tests only cover the opt-in
`service_supervisor` path.
"""
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
from frontend.desktop.shell.background.background_service_registry import BackgroundServiceRegistry
from frontend.desktop.shell.background.background_service_state import BackgroundServiceState
from frontend.desktop.shell.background.background_service_supervisor import BackgroundServiceSupervisor
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.ui.shell.conftest import make_context
from tests.unit.shell.background.conftest import RecordingService


def _router() -> DesktopRouter:
    return DesktopRouter(
        route_registry=RouteRegistry(), view_factory_registry=ViewFactoryRegistry(),
        initial_context=make_context(),
    )


def test_window_without_service_supervisor_still_works():
    win = ApplicationWindow(router=_router())
    assert win.service_supervisor is None


def test_bound_service_is_started_at_construction():
    registry = BackgroundServiceRegistry()
    registry.register(BackgroundServiceDescriptor(service_id="sync", display_name="Sync"))
    supervisor = BackgroundServiceSupervisor(registry=registry)
    service = RecordingService()
    supervisor.bind("sync", service)

    ApplicationWindow(router=_router(), service_supervisor=supervisor)
    assert service.start_calls == 1
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING


def test_unbound_registered_service_is_left_not_started():
    registry = BackgroundServiceRegistry()
    registry.register(BackgroundServiceDescriptor(service_id="sync", display_name="Sync"))
    supervisor = BackgroundServiceSupervisor(registry=registry)

    ApplicationWindow(router=_router(), service_supervisor=supervisor)  # must not raise
    assert supervisor.state_of("sync") is BackgroundServiceState.NOT_STARTED


def test_supervisor_is_reachable_from_the_window_for_health_inspection():
    registry = BackgroundServiceRegistry()
    registry.register(BackgroundServiceDescriptor(service_id="sync", display_name="Sync"))
    supervisor = BackgroundServiceSupervisor(registry=registry)
    supervisor.bind("sync", RecordingService())

    win = ApplicationWindow(router=_router(), service_supervisor=supervisor)
    assert win.service_supervisor.health_report().overall_status.value == "HEALTHY"
