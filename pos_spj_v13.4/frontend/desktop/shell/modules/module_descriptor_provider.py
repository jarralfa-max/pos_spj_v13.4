"""ModuleDescriptorProvider — SHELL-8.

Deliberately not named `ModuleProvider`: `backend.bootstrap.module_provider.
ModuleProvider` already exists (SHELL-5) and means something different —
"register services into a `ServiceRegistry`." This is "describe one module
for the `ModuleRegistry`" — a bounded context provides its own descriptor
(routes, permissions, health requirements, ...) without either provider
needing to know the other exists.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor


@runtime_checkable
class ModuleDescriptorProvider(Protocol):
    def describe(self) -> ModuleDescriptor: ...
