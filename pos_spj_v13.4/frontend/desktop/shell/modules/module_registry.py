"""ModuleRegistry — SHELL-8 §43.

Collects `ModuleDescriptor`s. Duplicate `module_id` fails eagerly at
`register()` — same discipline `ServiceRegistry` (SHELL-5) uses for
duplicate keys, not deferred to a later validation pass.
"""
from __future__ import annotations

from backend.bootstrap.health.health_status import HealthReport
from frontend.desktop.shell.modules.errors import DuplicateModuleRegistrationError, ModuleNotFoundError
from frontend.desktop.shell.modules.health_requirement import ModuleHealthEvaluator
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_descriptor_provider import ModuleDescriptorProvider
from frontend.desktop.shell.modules.startup_mode import StartupMode


class ModuleRegistry:
    def __init__(self, *, health_evaluator: ModuleHealthEvaluator | None = None) -> None:
        self._modules: dict[str, ModuleDescriptor] = {}
        self._health_evaluator = health_evaluator or ModuleHealthEvaluator()

    def register(self, descriptor: ModuleDescriptor) -> None:
        if descriptor.module_id in self._modules:
            raise DuplicateModuleRegistrationError(
                f"'{descriptor.module_id}' ya está registrado — cada módulo se registra una sola vez."
            )
        self._modules[descriptor.module_id] = descriptor

    def register_from_provider(self, provider: ModuleDescriptorProvider) -> None:
        self.register(provider.describe())

    def is_registered(self, module_id: str) -> bool:
        return module_id in self._modules

    def get(self, module_id: str) -> ModuleDescriptor | None:
        return self._modules.get(module_id)

    def require(self, module_id: str) -> ModuleDescriptor:
        descriptor = self.get(module_id)
        if descriptor is None:
            raise ModuleNotFoundError(f"Ningún módulo registrado con id '{module_id}'.")
        return descriptor

    def all(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(self._modules.values())

    def by_startup_mode(self, mode: StartupMode) -> tuple[ModuleDescriptor, ...]:
        return tuple(m for m in self._modules.values() if m.startup_mode is mode)

    def owner_of_route(self, route_id: str) -> str | None:
        """Which module_id declares `route_id` — None if no module does, or
        the special sentinel `"__DUPLICATE__"` if more than one does (a
        wiring bug for RouteRegistry, SHELL-9, to reject outright)."""
        owners = [m.module_id for m in self._modules.values() if route_id in m.routes]
        if not owners:
            return None
        if len(owners) > 1:
            return "__DUPLICATE__"
        return owners[0]

    def usable_modules(self, health_report: HealthReport) -> tuple[ModuleDescriptor, ...]:
        """Modules whose `health_requirements` are all satisfied by
        `health_report` — everything else is left out, not shown broken."""
        return tuple(
            m for m in self._modules.values()
            if self._health_evaluator.is_satisfied(m.health_requirements, health_report)
        )
