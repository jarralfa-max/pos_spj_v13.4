"""ModuleActivator — SHELL-13.

The pluggable "what does loading a module actually do" port `ModuleLoader`
calls through. Deliberately abstract: activating a module might register
view factories, wire a presenter, warm a connection — this phase doesn't
know or care, only that it either succeeds or raises. The real
implementation is SHELL-16's job (migrating each module off `AppContainer`
module by module); until then, callers supply their own — a stub that
does nothing for tests that don't care, or one that registers view
factories into a `ViewFactoryRegistry` for callers that do.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor


@runtime_checkable
class ModuleActivator(Protocol):
    def activate(self, module: ModuleDescriptor) -> None: ...
