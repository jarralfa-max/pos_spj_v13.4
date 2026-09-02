"""ShutdownCoordinator — SHELL-15.

Runs a fixed sequence of `ShutdownStep`s and produces one `ShutdownResult`
— the teardown mirror of SHELL-3's `DesktopApplicationBootstrapper`, with
one deliberate, important divergence: **it never stops early.**
`DesktopApplicationBootstrapper` stops at the first FATAL result because
later boot steps assume earlier ones succeeded (§9: "no continuar después
de un fallo fatal"). Shutdown has the opposite dependency shape — skipping
a cleanup step because an *earlier* cleanup step failed would leak more
resources, not fewer (a DB connection that never gets closed because the
outbox flush timed out first is strictly worse than closing it anyway).
So every step always runs, its result is recorded, and the coordinator
moves on regardless of status.

An unhandled exception from a step itself (not one the step caught and
reported via `ShutdownStepResult.failed()`) is treated as a FAILED result
for that step — same "an exception from a check is itself a finding"
discipline `ApplicationHealthCheckRunner` (SHELL-3) uses — rather than
propagating out and aborting every step after it.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from frontend.desktop.shell.shutdown.shutdown_context import ShutdownContext
from frontend.desktop.shell.shutdown.shutdown_result import ShutdownResult
from frontend.desktop.shell.shutdown.shutdown_step import ShutdownStep
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepResult, ShutdownStepStatus


class ShutdownCoordinator:
    def __init__(self, steps: list[ShutdownStep]) -> None:
        self._steps = steps

    def shutdown(self, context: ShutdownContext | None = None) -> ShutdownResult:
        context = context or ShutdownContext()
        started_at = datetime.now(timezone.utc)
        results: list[ShutdownStepResult] = []

        for step in self._steps:
            t0 = time.perf_counter()
            try:
                result = step.run(context)
            except Exception as exc:  # noqa: BLE001 - an unhandled step exception must not abort the rest
                result = ShutdownStepResult.failed(
                    step.name, f"Excepción no controlada en el paso '{step.name}': {exc}", exception=exc,
                )
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(result.with_duration(duration_ms))

        completed_at = datetime.now(timezone.utc)
        success = not any(r.status is ShutdownStepStatus.FAILED for r in results)
        warnings = tuple(r.message for r in results if r.status is ShutdownStepStatus.WARNING)

        return ShutdownResult(
            success=success, step_results=tuple(results), warnings=warnings,
            started_at=started_at, completed_at=completed_at,
        )
