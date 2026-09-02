"""BackgroundServiceDescriptor — SHELL-14.

The typed shape SHELL-8's `ModuleDescriptor.background_handlers` (plain
strings) pointed at without building — same deferral `NavigationItemDefinition`
(SHELL-12) and the `StartupMode`-driven loader (SHELL-13) resolved for
`navigation_items`/`StartupMode`. `module_id` links a service back to the
module that owns it, matching `NavigationItemDefinition.module_id`'s role.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundServiceDescriptor:
    service_id: str
    display_name: str
    module_id: str = ""

    def __post_init__(self) -> None:
        if not self.service_id or not self.service_id.strip():
            raise ValueError("service_id no puede estar vacío.")
        if not self.display_name or not self.display_name.strip():
            raise ValueError("display_name no puede estar vacío.")
