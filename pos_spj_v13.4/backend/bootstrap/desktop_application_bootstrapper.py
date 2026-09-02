"""DesktopApplicationBootstrapper — SHELL-3 §7.

Runs a fixed sequence of `BootstrapStep`s, stops at the first FATAL result
(§9: "no continuar después de un fallo fatal"), and produces one
`BootstrapResult` plus a `HealthReport`. Steps are injected, not
hardcoded — this class knows nothing about databases, migrations, or
installations; that knowledge lives in `backend/bootstrap/steps/`.

Not wired into `main.py` yet — see `docs/refactor/` for the legacy
inventory this will eventually replace. Building it standalone and tested
first (matching how SHELL-1/SHELL-2 were built) means main.py's cutover is
a small, low-risk swap once the remaining steps (composition root,
authentication, shell) exist.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_result import BootstrapResult
from backend.bootstrap.bootstrap_severity import BootstrapSeverity
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step import BootstrapStep
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.bootstrap.health.application_health_check_runner import ApplicationHealthCheckRunner


class DesktopApplicationBootstrapper:
    def __init__(
        self, steps: list[BootstrapStep], *, health_check_runner: ApplicationHealthCheckRunner | None = None,
    ) -> None:
        self._steps = steps
        self._health_check_runner = health_check_runner

    def bootstrap(self, context: BootstrapContext) -> BootstrapResult:
        started_at = datetime.now(timezone.utc)
        step_results: list[BootstrapStepResult] = []
        final_state = BootstrapState.CREATED
        failed = False

        for step in self._steps:
            t0 = time.perf_counter()
            try:
                result = step.run(context)
            except Exception as exc:  # noqa: BLE001 - an unhandled step exception is itself a fatal finding
                from backend.bootstrap.bootstrap_severity import BootstrapFailureReason

                result = BootstrapStepResult.fatal(
                    step.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                    f"Excepción no controlada en el paso '{step.name}': {exc}",
                    exception=exc,
                )
            duration_ms = (time.perf_counter() - t0) * 1000
            result = result.with_duration(duration_ms)
            step_results.append(result)

            if result.severity is BootstrapSeverity.FATAL:
                final_state = BootstrapState.FAILED
                failed = True
                break
            final_state = step.resulting_state

        if not failed:
            final_state = BootstrapState.RUNNING

        health_report = self._health_check_runner.run(context) if self._health_check_runner else None
        completed_at = datetime.now(timezone.utc)

        warnings = tuple(
            r.message for r in step_results if r.severity is BootstrapSeverity.WARNING
        )
        degraded_capabilities = tuple(
            cap for r in step_results for cap in r.degraded_capabilities
        )

        return BootstrapResult(
            success=not failed,
            exit_code=0 if not failed else 1,
            final_state=final_state,
            step_results=tuple(step_results),
            context=context,
            health_report=health_report,
            warnings=warnings,
            degraded_capabilities=degraded_capabilities,
            bootstrap_started_at=started_at,
            bootstrap_completed_at=completed_at,
        )
