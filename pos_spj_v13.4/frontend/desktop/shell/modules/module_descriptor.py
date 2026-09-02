"""ModuleDescriptor — SHELL-8 §43.

Every field the master plan lists. `routes`/`navigation_items` are plain
route-id strings for now, not `RouteDefinition`/`NavigationItemDefinition`
objects — those typed registries are SHELL-9/SHELL-12; a descriptor built
today just declares which ids it owns, and the router/sidebar validate
those ids resolve once they exist. `view_factories` is keyed by route id
(empty for every module until SHELL-16 migrates it off `AppContainer` and
gives it a real factory — an empty dict here is an honest "not migrated
yet," not a placeholder pretending to be one).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from frontend.desktop.shell.modules.health_requirement import HealthRequirement
from frontend.desktop.shell.modules.startup_mode import StartupMode


@dataclass(frozen=True)
class ModuleDescriptor:
    module_id: str
    display_name: str
    startup_mode: StartupMode = StartupMode.LAZY
    routes: tuple[str, ...] = field(default_factory=tuple)
    navigation_items: tuple[str, ...] = field(default_factory=tuple)
    permissions: frozenset[str] = field(default_factory=frozenset)
    feature_flags: tuple[str, ...] = field(default_factory=tuple)
    health_requirements: tuple[HealthRequirement, ...] = field(default_factory=tuple)
    view_factories: dict[str, Callable] = field(default_factory=dict)
    background_handlers: tuple[str, ...] = field(default_factory=tuple)
    required_services: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.module_id or not self.module_id.strip():
            raise ValueError("module_id no puede estar vacío.")
        if not self.display_name or not self.display_name.strip():
            raise ValueError("display_name no puede estar vacío.")
