"""ModuleProvider — SHELL-5 §14.

One provider per bounded context (`backend/bootstrap/wiring/`). A provider
only ever sees a `ServiceRegistry` — registration, never resolution — so
wiring one module can't accidentally reach into another module's instances
before the whole graph is built and validated.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.bootstrap.service_registry import ServiceRegistry


@runtime_checkable
class ModuleProvider(Protocol):
    def register(self, registry: ServiceRegistry) -> None: ...
