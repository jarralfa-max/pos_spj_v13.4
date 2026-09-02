"""IntegrationHealthPolicy — SET-19 "Health": derives an
`IntegrationHealthStatus` from an `IntegrationInstance`'s
`IntegrationHealthCheck` history. Pure computation over already-recorded
checks — no I/O, no polling; a future use case is responsible for
actually calling out and recording the result.
"""

from __future__ import annotations

from backend.domain.integrations.entities.integration_health_check import IntegrationHealthCheck
from backend.domain.integrations.enums import IntegrationHealthStatus


def current_status(checks: list[IntegrationHealthCheck]) -> IntegrationHealthStatus:
    if not checks:
        return IntegrationHealthStatus.UNKNOWN
    ordered = sorted(checks, key=lambda check: check.checked_at)
    latest = ordered[-1]
    if latest.success:
        return IntegrationHealthStatus.HEALTHY
    if any(check.success for check in ordered):
        return IntegrationHealthStatus.DEGRADED
    return IntegrationHealthStatus.DOWN
