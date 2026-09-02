"""ApplicationWindow + ShutdownCoordinator wiring — SHELL-15.

Additive to SHELL-11's `test_application_window.py`, which exercises
`ApplicationWindow` with `shutdown_coordinator=None` (the default) and
must keep passing unmodified — these tests only cover the opt-in
`shutdown_coordinator` path.
"""
from PyQt5.QtGui import QCloseEvent

from frontend.desktop.shell.application_shell.application_window import ApplicationWindow
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from frontend.desktop.shell.shutdown.shutdown_coordinator import ShutdownCoordinator
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult
from tests.ui.shell.conftest import make_context
from tests.unit.shell.shutdown.conftest import RecordingStep


def _router() -> DesktopRouter:
    return DesktopRouter(
        route_registry=RouteRegistry(), view_factory_registry=ViewFactoryRegistry(),
        initial_context=make_context(),
    )


def test_window_without_shutdown_coordinator_close_event_does_not_raise():
    win = ApplicationWindow(router=_router())
    win.closeEvent(QCloseEvent())  # must not raise
    assert win.last_shutdown_result is None


def test_close_event_runs_the_shutdown_coordinator():
    step = RecordingStep("workers")
    win = ApplicationWindow(router=_router(), shutdown_coordinator=ShutdownCoordinator([step]))
    win.closeEvent(QCloseEvent())
    assert step.ran is True


def test_close_event_stores_the_shutdown_result():
    coordinator = ShutdownCoordinator([RecordingStep("workers")])
    win = ApplicationWindow(router=_router(), shutdown_coordinator=coordinator)
    win.closeEvent(QCloseEvent())
    assert win.last_shutdown_result is not None
    assert win.last_shutdown_result.success is True


def test_close_event_captures_a_failed_shutdown_result_without_raising():
    failing_step = RecordingStep("connections", ShutdownStepResult.failed("connections", "disk full"))
    coordinator = ShutdownCoordinator([failing_step])
    win = ApplicationWindow(router=_router(), shutdown_coordinator=coordinator)
    win.closeEvent(QCloseEvent())  # must not raise even though the shutdown itself failed
    assert win.last_shutdown_result.success is False
