"""HealthReport data types — SHELL-3 §69.

`HealthStatus` ordering (worst to best) is what
`ApplicationHealthCheckRunner` uses to roll individual check results up
into one `overall_status`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"


# Worst-first — index is severity rank, lower is worse.
_SEVERITY_ORDER = (
    HealthStatus.UNHEALTHY, HealthStatus.DEGRADED, HealthStatus.UNKNOWN, HealthStatus.HEALTHY,
)


def worse_of(a: HealthStatus, b: HealthStatus) -> HealthStatus:
    return a if _SEVERITY_ORDER.index(a) <= _SEVERITY_ORDER.index(b) else b


def is_at_least(status: HealthStatus, minimum: HealthStatus) -> bool:
    """True if `status` is at least as good as `minimum` (e.g. HEALTHY is at
    least DEGRADED). Single source of truth for severity ordering — SHELL-8's
    `ModuleHealthEvaluator` uses this rather than re-deriving the ranking."""
    return _SEVERITY_ORDER.index(status) >= _SEVERITY_ORDER.index(minimum)


@dataclass(frozen=True)
class HealthCheckResult:
    check_name: str
    status: HealthStatus
    message: str = ""


@dataclass(frozen=True)
class HealthReport:
    overall_status: HealthStatus
    checks: tuple[HealthCheckResult, ...]
    generated_at: datetime

    def is_healthy(self) -> bool:
        return self.overall_status is HealthStatus.HEALTHY

    def failing_checks(self) -> tuple[HealthCheckResult, ...]:
        return tuple(c for c in self.checks if c.status is not HealthStatus.HEALTHY)
