"""HealthCheck — SHELL-3 §69."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.health.health_status import HealthCheckResult


@runtime_checkable
class HealthCheck(Protocol):
    name: str

    def check(self, context: BootstrapContext) -> HealthCheckResult: ...
