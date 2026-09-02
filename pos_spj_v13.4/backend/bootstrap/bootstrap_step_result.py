"""BootstrapStepResult — SHELL-3.

What every `BootstrapStep.run()` returns. Fields match the master refactor
plan §8 exactly. `duration_ms` is filled in by
`DesktopApplicationBootstrapper`, not the step itself — steps shouldn't have
to thread a stopwatch through their own logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.bootstrap.bootstrap_severity import BootstrapFailureReason, BootstrapSeverity, severity_for


@dataclass(frozen=True)
class BootstrapStepResult:
    step_name: str
    success: bool
    severity: BootstrapSeverity
    message: str
    exception_type: str | None = None
    technical_details: str | None = None
    degraded_capabilities: tuple[str, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0

    def with_duration(self, duration_ms: float) -> "BootstrapStepResult":
        return BootstrapStepResult(
            step_name=self.step_name, success=self.success, severity=self.severity,
            message=self.message, exception_type=self.exception_type,
            technical_details=self.technical_details,
            degraded_capabilities=self.degraded_capabilities, duration_ms=duration_ms,
        )

    # ── Factories — the only way to build a result, so severity always ─────
    # comes from `severity_for()` rather than a step inventing its own.

    @classmethod
    def ok(cls, step_name: str, message: str = "") -> "BootstrapStepResult":
        return cls(step_name=step_name, success=True, severity=BootstrapSeverity.INFO, message=message)

    @classmethod
    def warning(
        cls, step_name: str, reason: BootstrapFailureReason, message: str,
    ) -> "BootstrapStepResult":
        severity = severity_for(reason)
        if severity is not BootstrapSeverity.WARNING:
            raise ValueError(f"{reason!r} no clasifica como WARNING (es {severity.value}).")
        return cls(step_name=step_name, success=True, severity=severity, message=message)

    @classmethod
    def degraded(
        cls, step_name: str, reason: BootstrapFailureReason, message: str,
        *, degraded_capabilities: tuple[str, ...] = (),
    ) -> "BootstrapStepResult":
        severity = severity_for(reason)
        if severity is not BootstrapSeverity.DEGRADED:
            raise ValueError(f"{reason!r} no clasifica como DEGRADED (es {severity.value}).")
        return cls(
            step_name=step_name, success=True, severity=severity, message=message,
            degraded_capabilities=degraded_capabilities or (reason.value,),
        )

    @classmethod
    def fatal(
        cls, step_name: str, reason: BootstrapFailureReason, message: str,
        *, exception: BaseException | None = None,
    ) -> "BootstrapStepResult":
        severity = severity_for(reason)
        if severity is not BootstrapSeverity.FATAL:
            raise ValueError(f"{reason!r} no clasifica como FATAL (es {severity.value}).")
        return cls(
            step_name=step_name, success=False, severity=severity, message=message,
            exception_type=type(exception).__name__ if exception else None,
            technical_details=str(exception) if exception else None,
        )
