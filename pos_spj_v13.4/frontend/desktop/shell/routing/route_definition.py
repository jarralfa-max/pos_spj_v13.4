"""RouteDefinition — SHELL-9 §45.

`route_id` must be dotted `module.action` form (`sales.pos`,
`inventory.overview`) — never a bare legacy code like `POS`/`CAJA`
(§45's explicit prohibition; enforced by `RouteRegistryValidator`, not
here, so a malformed id can still be constructed and inspected in tests
before deciding what to do with it).
"""
from __future__ import annotations

from dataclasses import dataclass

from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy


@dataclass(frozen=True)
class RouteDefinition:
    route_id: str
    module_id: str
    title: str
    view_factory_id: str
    breadcrumb: tuple[str, ...] = ()
    required_permission: str = ""
    feature_flag: str = ""
    startup_mode: StartupMode = StartupMode.LAZY
    cache_policy: CachePolicy = CachePolicy.RECREATE_ON_NAVIGATION
    offline_policy: OfflinePolicy = OfflinePolicy.REQUIRES_ONLINE

    def __post_init__(self) -> None:
        if not self.route_id or not self.route_id.strip():
            raise ValueError("route_id no puede estar vacío.")
        if not self.module_id or not self.module_id.strip():
            raise ValueError("module_id no puede estar vacío.")
        if not self.title or not self.title.strip():
            raise ValueError("title no puede estar vacío.")
        if not self.view_factory_id or not self.view_factory_id.strip():
            raise ValueError("view_factory_id no puede estar vacío.")
