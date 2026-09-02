"""DesktopRouter — SHELL-10.

Ties SHELL-9's `RouteRegistry`/`ViewFactoryRegistry` and SHELL-6's
`ApplicationContext`/`PermissionEvaluator` together into the single place
that answers "can this navigation happen right now, and if so, here's the
view." Every `navigate()` call re-evaluates permission, feature flag, and
offline policy against the *current* context — nothing is cached from a
previous check, so a context swap (`update_context()`, e.g. after
`ApplicationContextService.change_branch()`) takes effect on the very next
navigation without any extra invalidation step.

Deliberately out of scope for this phase (left to the phases whose job the
master plan assigns them to):
- View caching/reuse per `route.cache_policy` — `ContentHost` (SHELL-11).
  `navigate()` always constructs a fresh view via the view factory; the
  `NavigationResult.route.cache_policy` is exposed so `ContentHost` can act
  on it once it exists.
- Sidebar/breadcrumb rendering from `route.breadcrumb` — SHELL-12.
- Real connectivity detection — `context.offline_status` is trusted as
  given; whatever sets it (a connectivity monitor) is a separate concern.
"""
from __future__ import annotations

from typing import Callable, Optional

from backend.bootstrap.application_context import ApplicationContext
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from frontend.desktop.shell.router.errors import (
    NavigationFeatureDisabledError,
    NavigationPermissionDeniedError,
    NavigationRequiresOnlineError,
)
from frontend.desktop.shell.router.navigation_events import (
    NAVIGATION_BACK,
    NAVIGATION_DENIED,
    NAVIGATION_FORWARD,
    NAVIGATION_REQUESTED,
    NAVIGATION_SUCCEEDED,
)
from frontend.desktop.shell.router.navigation_history import NavigationHistory
from frontend.desktop.shell.router.navigation_result import NavigationResult
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry

EventPublisher = Callable[[str, dict], None]


class DesktopRouter:
    def __init__(
        self,
        *,
        route_registry: RouteRegistry,
        view_factory_registry: ViewFactoryRegistry,
        initial_context: ApplicationContext,
        event_publisher: Optional[EventPublisher] = None,
    ) -> None:
        self._routes = route_registry
        self._views = view_factory_registry
        self._context = initial_context
        self._history = NavigationHistory()
        self._publish = event_publisher or (lambda event, payload: None)

    @property
    def current_context(self) -> ApplicationContext:
        return self._context

    @property
    def route_registry(self) -> RouteRegistry:
        return self._routes

    @property
    def current_route_id(self) -> str | None:
        return self._history.current()

    def update_context(self, context: ApplicationContext) -> None:
        """Swap the context used by every subsequent permission/feature/
        offline check. Does not itself re-navigate or invalidate any view —
        whether the currently displayed route is still valid under the new
        context is `current_route_still_allowed()`'s question to answer,
        left to the caller to act on."""
        self._context = context

    def current_route_still_allowed(self) -> bool:
        route_id = self._history.current()
        if route_id is None:
            return True
        route = self._routes.get(route_id)
        if route is None:
            return False
        try:
            self._authorize(route)
        except NavigationPermissionDeniedError:
            return False
        except NavigationFeatureDisabledError:
            return False
        return True

    def can_go_back(self) -> bool:
        return self._history.can_go_back()

    def can_go_forward(self) -> bool:
        return self._history.can_go_forward()

    def navigate(self, route_id: str) -> NavigationResult:
        self._publish(NAVIGATION_REQUESTED, {"route_id": route_id, "user_id": self._context.user_id})
        route = self._routes.require(route_id)
        result = self._build_result(route)
        self._history.push(route_id)
        self._publish(NAVIGATION_SUCCEEDED, {"route_id": route_id, "user_id": self._context.user_id})
        return result

    def go_back(self) -> NavigationResult:
        route_id = self._history.peek_back()
        route = self._routes.require(route_id)
        result = self._build_result(route)
        self._history.commit_back()
        self._publish(NAVIGATION_BACK, {"route_id": route_id, "user_id": self._context.user_id})
        return result

    def go_forward(self) -> NavigationResult:
        route_id = self._history.peek_forward()
        route = self._routes.require(route_id)
        result = self._build_result(route)
        self._history.commit_forward()
        self._publish(NAVIGATION_FORWARD, {"route_id": route_id, "user_id": self._context.user_id})
        return result

    def _build_result(self, route: RouteDefinition) -> NavigationResult:
        self._authorize(route)
        degraded = self._check_offline(route)
        view = self._views.create_view(route.view_factory_id)
        return NavigationResult(route=route, view=view, context=self._context, degraded_offline=degraded)

    def _authorize(self, route: RouteDefinition) -> None:
        if route.required_permission:
            evaluator = PermissionEvaluator(self._context)
            if not evaluator.has_permission(route.required_permission):
                self._publish(NAVIGATION_DENIED, {"route_id": route.route_id, "reason": "PERMISSION"})
                raise NavigationPermissionDeniedError(
                    f"No tiene permiso '{route.required_permission}' para acceder a '{route.route_id}'."
                )
        if route.feature_flag and not self._context.feature_context.is_enabled(route.feature_flag):
            self._publish(NAVIGATION_DENIED, {"route_id": route.route_id, "reason": "FEATURE_DISABLED"})
            raise NavigationFeatureDisabledError(
                f"La función '{route.feature_flag}' está deshabilitada para '{route.route_id}'."
            )

    def _check_offline(self, route: RouteDefinition) -> bool:
        if self._context.offline_status != "OFFLINE":
            return False
        if route.offline_policy is OfflinePolicy.REQUIRES_ONLINE:
            self._publish(NAVIGATION_DENIED, {"route_id": route.route_id, "reason": "REQUIRES_ONLINE"})
            raise NavigationRequiresOnlineError(
                f"'{route.route_id}' requiere conexión a internet y no hay conectividad."
            )
        return route.offline_policy is OfflinePolicy.DEGRADED_OFFLINE
