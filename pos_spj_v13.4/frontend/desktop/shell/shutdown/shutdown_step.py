"""ShutdownStep — SHELL-15."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


@runtime_checkable
class ShutdownStep(Protocol):
    name: str

    def run(self, context: ShutdownContext) -> ShutdownStepResult: ...
