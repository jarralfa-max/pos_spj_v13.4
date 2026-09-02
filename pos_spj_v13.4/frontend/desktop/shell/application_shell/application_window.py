"""ApplicationWindow — SHELL-11, extended in SHELL-12.

Composes `TopBar` + `ContentHost` + `NotificationDrawer` + `StatusBar`
around SHELL-10's `DesktopRouter`, plus SHELL-12's `GlobalSidebar` (an
optional, opt-in dependency — see below). A real `QMainWindow` — the shell
chrome the legacy `AppContainer`/`MainWindow`/`MenuLateral` trio
(CLAUDE.md's "SHIMS Y COMPATIBILIDAD" section) will eventually be replaced
by, once SHELL-16 migrates every module off `AppContainer` and SHELL-17
deletes the legacy classes.

`sidebar`, `module_loader`, and `service_supervisor` all default to `None`
(inert) rather than being required — constructing a real `GlobalSidebar`/
`ModuleLoader`/`BackgroundServiceSupervisor` needs wiring most existing/
future callers (including every SHELL-11 test) don't have yet, and those
tests must keep passing unmodified. When a `sidebar` is given, its
`item_activated` is wired straight into `navigate()`, and
`set_active_route()` is refreshed after every successful navigation. When
a `module_loader` is given, `EAGER` modules are activated and
`BACKGROUND_PRELOAD` modules are scheduled once, at construction, and
every `navigate()` call runs `ensure_loaded()` for the target route's
module first — SHELL-13's lazy-loading/error-view behavior. When a
`service_supervisor` is given, every bound background service is started
once, at construction (SHELL-14) — this window has no opinion on *which*
services exist or run health polling on them afterward; a caller inspects
`service_supervisor.health_report()` on its own schedule. When a
`shutdown_coordinator` is given (SHELL-15), `closeEvent()` runs it before
accepting the close — the natural Qt teardown hook — and stores the
outcome in `last_shutdown_result` for inspection; without one, `closeEvent()`
falls back to the base `QMainWindow` behavior, unchanged from SHELL-11.

Deliberately standalone here: not wired into `main.py`, and not itself
deciding *which* route to show first or what the sidebar's item list is —
a caller drives navigation via `navigate()`/`go_back()`/`go_forward()` and
populates the sidebar via `GlobalSidebar.set_items()` directly, same as it
would drive `DesktopRouter` directly.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from backend.bootstrap.application_context import ApplicationContext
from frontend.desktop.shell.application_shell.content_host import ContentHost
from frontend.desktop.shell.background.background_service_supervisor import BackgroundServiceSupervisor
from frontend.desktop.shell.application_shell.notification_drawer import NotificationDrawer
from frontend.desktop.shell.application_shell.status_bar import StatusBar
from frontend.desktop.shell.application_shell.top_bar import TopBar
from frontend.desktop.shell.loading.module_error_view import build_module_error_view
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState
from frontend.desktop.shell.loading.module_loader import ModuleLoader, Scheduler, immediate_scheduler
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.shutdown.shutdown_coordinator import ShutdownCoordinator
from frontend.desktop.shell.shutdown.shutdown_result import ShutdownResult
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar


class ApplicationWindow(QMainWindow):
    def __init__(
        self, *, router: DesktopRouter, sidebar: GlobalSidebar | None = None,
        module_loader: ModuleLoader | None = None,
        background_preload_scheduler: Scheduler = immediate_scheduler,
        service_supervisor: BackgroundServiceSupervisor | None = None,
        shutdown_coordinator: ShutdownCoordinator | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("applicationWindow")
        self._router = router
        self._module_loader = module_loader
        self.service_supervisor = service_supervisor
        self.shutdown_coordinator = shutdown_coordinator
        self.last_shutdown_result: ShutdownResult | None = None

        self.top_bar = TopBar(self)
        self.content_host = ContentHost(self)
        self.notification_drawer = NotificationDrawer(self)
        self.status_bar = StatusBar(self)
        self.sidebar = sidebar

        self.top_bar.notifications_toggled.connect(self.notification_drawer.toggle)
        self.notification_drawer.unread_count_changed.connect(self.top_bar.set_unread_notification_count)
        if self.sidebar is not None:
            self.sidebar.item_activated.connect(self.navigate)

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        if self.sidebar is not None:
            body.addWidget(self.sidebar, 0)
        body.addWidget(self.content_host, 1)
        body.addWidget(self.notification_drawer, 0)
        outer.addLayout(body)

        self.setCentralWidget(central)
        self.setStatusBar(self.status_bar)

        self._apply_context(router.current_context)

        if self._module_loader is not None:
            self._module_loader.load_eager_modules()
            self._module_loader.schedule_background_preload(background_preload_scheduler)

        if self.service_supervisor is not None:
            self.service_supervisor.start_all()

    @property
    def router(self) -> DesktopRouter:
        return self._router

    def navigate(self, route_id: str) -> NavigationResult:
        if self._module_loader is not None:
            route = self._router.route_registry.get(route_id)
            if route is not None:
                load_result = self._module_loader.ensure_loaded(route.module_id)
                if load_result.state is ModuleLoadState.FAILED:
                    result = self._build_error_result(route, load_result.error)
                    self._show_error(result)
                    return result
        result = self._router.navigate(route_id)
        self._show(result)
        return result

    def go_back(self) -> NavigationResult:
        result = self._router.go_back()
        self._show(result)
        return result

    def go_forward(self) -> NavigationResult:
        result = self._router.go_forward()
        self._show(result)
        return result

    def update_context(self, context: ApplicationContext) -> None:
        self._router.update_context(context)
        self.content_host.on_context_changed()
        self._apply_context(context)

    def _show(self, result: NavigationResult) -> None:
        self.content_host.display(result)
        self.top_bar.set_breadcrumb(result.route.breadcrumb)
        self.status_bar.set_offline_status(result.context.offline_status, degraded=result.degraded_offline)
        if self.sidebar is not None:
            self.sidebar.set_active_route(result.route.route_id)

    def _apply_context(self, context: ApplicationContext) -> None:
        self.top_bar.set_context(context)
        self.status_bar.set_workstation(context.workstation_id, context.branch_name)
        self.status_bar.set_offline_status(context.offline_status)

    def _build_error_result(self, route: RouteDefinition, error: BaseException) -> NavigationResult:
        view = build_module_error_view(
            route.module_id, error, on_retry=lambda: self.navigate(route.route_id),
        )
        return NavigationResult(
            route=route, view=view, context=self._router.current_context, load_failed=True,
        )

    def _show_error(self, result: NavigationResult) -> None:
        # Deliberately narrower than `_show()`: a failed load must not
        # advance `DesktopRouter`'s history/current_route_id (never called
        # here) or the sidebar's highlighted item — both should still point
        # at wherever the user actually is, not the broken destination they
        # tried to reach. Only the content area and breadcrumb reflect the
        # attempt, so a retry has something concrete to react to.
        self.content_host.display(result)
        self.top_bar.set_breadcrumb(result.route.breadcrumb)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's own method name
        if self.shutdown_coordinator is not None:
            self.last_shutdown_result = self.shutdown_coordinator.shutdown()
        super().closeEvent(event)
