"""BootstrapStep — SHELL-3.

Every concrete step (see `backend/bootstrap/steps/`) implements this
Protocol: a `name`, the `BootstrapState` it represents once it succeeds, and
`run()`. `DesktopApplicationBootstrapper` treats steps opaquely — it never
special-cases a step by name, so new phases (SHELL-4 onward) register their
own steps into the same engine without touching it.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult


@runtime_checkable
class BootstrapStep(Protocol):
    name: str
    resulting_state: BootstrapState

    def run(self, context: BootstrapContext) -> BootstrapStepResult: ...
