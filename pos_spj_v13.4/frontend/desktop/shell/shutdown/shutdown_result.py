"""ShutdownResult — SHELL-15. Mirrors SHELL-3's `BootstrapResult` shape."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult


@dataclass(frozen=True)
class ShutdownResult:
    success: bool
    step_results: tuple[ShutdownStepResult, ...]
    warnings: tuple[str, ...]
    started_at: datetime
    completed_at: datetime
