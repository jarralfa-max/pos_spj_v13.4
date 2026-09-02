"""ApplicationHealthCheckRunner — SHELL-3 §69.

Runs every registered `HealthCheck` and rolls the results up into one
`HealthReport`. A check that raises is treated as UNHEALTHY rather than
crashing the whole report — the point of a health report is to describe
what's wrong, not to join in.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.health.health_check import HealthCheck
from backend.bootstrap.health.health_status import HealthCheckResult, HealthReport, HealthStatus, worse_of


class ApplicationHealthCheckRunner:
    def __init__(self, checks: list[HealthCheck]) -> None:
        self._checks = checks

    def run(self, context: BootstrapContext) -> HealthReport:
        results = []
        overall = HealthStatus.HEALTHY
        for check in self._checks:
            try:
                result = check.check(context)
            except Exception as exc:  # noqa: BLE001 - a broken check is itself a health finding
                result = HealthCheckResult(
                    check_name=getattr(check, "name", check.__class__.__name__),
                    status=HealthStatus.UNHEALTHY,
                    message=f"El chequeo falló con una excepción: {exc}",
                )
            results.append(result)
            overall = worse_of(overall, result.status)
        return HealthReport(
            overall_status=overall, checks=tuple(results),
            generated_at=datetime.now(timezone.utc),
        )
