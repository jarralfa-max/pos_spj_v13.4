"""ShutdownStepResult — SHELL-15.

What every `ShutdownStep.run()` returns. Deliberately lighter than SHELL-3's
`BootstrapStepResult`: bootstrap needs the full FATAL/DEGRADED/WARNING
`BootstrapFailureReason` taxonomy because *which* failures must halt the
boot is a structural decision (§9). Shutdown never halts early (see
`ShutdownCoordinator`'s docstring) — there's nothing for a reason-to-
severity classifier to gate, so a plain three-way status plus a factory
per outcome is enough: `OK` (nothing to report), `WARNING` (shutdown still
succeeded, but something's worth surfacing — e.g. outbox items still
pending, to retry on next launch), `FAILED` (the step itself broke).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShutdownStepStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ShutdownStepResult:
    step_name: str
    status: ShutdownStepStatus
    message: str
    exception: BaseException | None = None
    duration_ms: float = 0.0

    def with_duration(self, duration_ms: float) -> "ShutdownStepResult":
        return ShutdownStepResult(
            step_name=self.step_name, status=self.status, message=self.message,
            exception=self.exception, duration_ms=duration_ms,
        )

    @classmethod
    def ok(cls, step_name: str, message: str = "") -> "ShutdownStepResult":
        return cls(step_name=step_name, status=ShutdownStepStatus.OK, message=message)

    @classmethod
    def warning(cls, step_name: str, message: str) -> "ShutdownStepResult":
        return cls(step_name=step_name, status=ShutdownStepStatus.WARNING, message=message)

    @classmethod
    def failed(
        cls, step_name: str, message: str, *, exception: BaseException | None = None,
    ) -> "ShutdownStepResult":
        return cls(step_name=step_name, status=ShutdownStepStatus.FAILED, message=message, exception=exception)
