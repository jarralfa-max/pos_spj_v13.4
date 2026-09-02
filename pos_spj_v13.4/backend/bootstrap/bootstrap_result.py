"""BootstrapResult — SHELL-3 §10.

`application_context`, `composition_root`, and `initial_window` are `object
| None` on purpose: those concrete types don't exist yet
(`ApplicationContext` is SHELL-6, `CompositionRoot` is SHELL-5,
`ApplicationShellWindow` is SHELL-11). The field names and slots are part of
the spec'd contract main.py will eventually read
(`result.initial_window.show()`); each later phase populates its own field
without needing to change this dataclass's shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.bootstrap.health.health_status import HealthReport


@dataclass(frozen=True)
class BootstrapResult:
    success: bool
    exit_code: int
    final_state: BootstrapState
    step_results: tuple[BootstrapStepResult, ...]
    context: BootstrapContext
    health_report: HealthReport | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    degraded_capabilities: tuple[str, ...] = field(default_factory=tuple)
    bootstrap_started_at: datetime | None = None
    bootstrap_completed_at: datetime | None = None

    # Populated starting in later phases — see module docstring.
    application_context: object | None = None
    composition_root: object | None = None
    initial_window: object | None = None

    def failed_step(self) -> BootstrapStepResult | None:
        for result in self.step_results:
            if not result.success:
                return result
        return None

    def duration_ms(self) -> float:
        if not self.bootstrap_started_at or not self.bootstrap_completed_at:
            return 0.0
        return (self.bootstrap_completed_at - self.bootstrap_started_at).total_seconds() * 1000
