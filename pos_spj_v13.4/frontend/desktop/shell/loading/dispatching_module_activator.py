"""DispatchingModuleActivator — SHELL-16.

`ModuleLoader` (SHELL-13) takes exactly one `ModuleActivator` — this is
that one activator for a real app with more than one module: a thin
router that looks up `module.module_id` in an injected mapping and
delegates to whichever per-module `ModuleActivator` is registered for it.
Each per-module activator (e.g. `frontend/desktop/modules/sales_pos/shell_registration.py::SalesPosModuleActivator`)
takes its own explicit, narrow dependencies — this class holds no
dependencies of its own beyond the mapping, and never sees `AppContainer`
or anything like it.

A module with no registered activator raises rather than silently no-op'ing
— an unregistered `module_id` reaching `activate()` means `ModuleLoader`
was asked to load something nothing actually knows how to build, which is
a wiring bug, not a valid "nothing to do" state.
"""
from __future__ import annotations

from frontend.desktop.shell.loading.module_activator import ModuleActivator
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor


class UnregisteredModuleActivatorError(KeyError):
    """`DispatchingModuleActivator.activate()` was asked to activate a
    `module_id` with no per-module `ModuleActivator` registered."""


class DispatchingModuleActivator:
    def __init__(self) -> None:
        self._activators: dict[str, ModuleActivator] = {}

    def register(self, module_id: str, activator: ModuleActivator) -> None:
        self._activators[module_id] = activator

    def is_registered(self, module_id: str) -> bool:
        return module_id in self._activators

    def activate(self, module: ModuleDescriptor) -> None:
        activator = self._activators.get(module.module_id)
        if activator is None:
            raise UnregisteredModuleActivatorError(
                f"Ningún ModuleActivator registrado para el módulo '{module.module_id}'."
            )
        activator.activate(module)
