"""NavigationResult — SHELL-10, extended in SHELL-13.

What `DesktopRouter.navigate()`/`go_back()`/`go_forward()` hand back: the
route that was resolved, the freshly-constructed view, the context it was
built under, and whether it's running in degraded-offline mode. Caching the
view across navigations (per `route.cache_policy`) is `ContentHost`'s job
(SHELL-11) — this result only carries a fresh view plus the policy the
caller needs to decide what to do with it.

`load_failed` (SHELL-13, default `False`): set by callers that build a
`NavigationResult` themselves after `ModuleLoader.ensure_loaded()` failed
(`DesktopRouter` itself never sets this — it doesn't know about module
loading). Tells `ContentHost` to show `view` without caching it under
`route.cache_policy` — an error placeholder shouldn't get `KEEP_ALIVE`'d
in place of the real view a retry might still produce.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.bootstrap.application_context import ApplicationContext
from frontend.desktop.shell.routing.route_definition import RouteDefinition


@dataclass(frozen=True)
class NavigationResult:
    route: RouteDefinition
    view: object
    context: ApplicationContext
    degraded_offline: bool = False
    load_failed: bool = False
