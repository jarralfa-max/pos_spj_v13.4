"""RouteRegistry — SHELL-9 §45.

Duplicate `route_id` fails eagerly at `register()`, same discipline as
`ServiceRegistry`/`ModuleRegistry`. Cross-registry consistency (does
`module_id` exist? does `view_factory_id` exist? is `route_id` ambiguous?)
is deliberately *not* checked here — that's `RouteRegistryValidator`'s job,
run once after every route is registered, so registration order never
matters and a single call reports every problem at once instead of failing
on whichever route happened to reference something unregistered first.
"""
from __future__ import annotations

from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.errors import DuplicateRouteRegistrationError, RouteNotFoundError
from frontend.desktop.shell.routing.route_definition import RouteDefinition


class RouteRegistry:
    def __init__(self) -> None:
        self._routes: dict[str, RouteDefinition] = {}

    def register(self, route: RouteDefinition) -> None:
        if route.route_id in self._routes:
            raise DuplicateRouteRegistrationError(
                f"'{route.route_id}' ya está registrado — cada ruta se registra una sola vez."
            )
        self._routes[route.route_id] = route

    def is_registered(self, route_id: str) -> bool:
        return route_id in self._routes

    def get(self, route_id: str) -> RouteDefinition | None:
        return self._routes.get(route_id)

    def require(self, route_id: str) -> RouteDefinition:
        route = self.get(route_id)
        if route is None:
            raise RouteNotFoundError(f"Ninguna ruta registrada con id '{route_id}'.")
        return route

    def all(self) -> tuple[RouteDefinition, ...]:
        return tuple(self._routes.values())

    def by_module_id(self, module_id: str) -> tuple[RouteDefinition, ...]:
        return tuple(r for r in self._routes.values() if r.module_id == module_id)

    def by_startup_mode(self, mode: StartupMode) -> tuple[RouteDefinition, ...]:
        return tuple(r for r in self._routes.values() if r.startup_mode is mode)
