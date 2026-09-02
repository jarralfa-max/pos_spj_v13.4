"""NavigationItemDefinition — SHELL-12.

The typed sidebar-item shape SHELL-8's `ModuleDescriptor.navigation_items`
docstring named but deliberately didn't build ("plain route-id strings for
now... those typed registries are SHELL-9/SHELL-12"). Distinct from
`RouteDefinition` (SHELL-9): a route is "what shows when you're here," a
nav item is "what appears in the sidebar to get you there" — `route_id` is
the bridge between them, resolved against the live `RouteRegistry` at
resolve time rather than duplicated here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationItemDefinition:
    item_id: str
    module_id: str
    route_id: str
    label: str
    icon: str
    order: int = 0
    group: str = ""
    required_permission: str = ""
    feature_flag: str = ""
    badge_key: str = ""

    def __post_init__(self) -> None:
        if not self.item_id or not self.item_id.strip():
            raise ValueError("item_id no puede estar vacío.")
        if not self.module_id or not self.module_id.strip():
            raise ValueError("module_id no puede estar vacío.")
        if not self.route_id or not self.route_id.strip():
            raise ValueError("route_id no puede estar vacío.")
        if not self.label or not self.label.strip():
            raise ValueError("label no puede estar vacío.")
        if not self.icon or not self.icon.strip():
            raise ValueError("icon no puede estar vacío.")
