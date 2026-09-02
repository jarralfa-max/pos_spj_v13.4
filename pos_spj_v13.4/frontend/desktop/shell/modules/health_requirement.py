"""HealthRequirement / ModuleHealthEvaluator — SHELL-8.

A module declares which SHELL-3 health checks it needs and at what minimum
`HealthStatus` — e.g. the (future) Inventory module might require
`database` and `schema` to be HEALTHY but tolerate `secret_store` being
DEGRADED. `ModuleHealthEvaluator` answers "given the app's current
`HealthReport`, is this module usable right now" without the module
needing to know anything about how health checks are run.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.bootstrap.health.health_status import HealthReport, HealthStatus, is_at_least


@dataclass(frozen=True)
class HealthRequirement:
    check_name: str
    minimum_status: HealthStatus = HealthStatus.HEALTHY


@dataclass(frozen=True)
class UnmetHealthRequirement:
    requirement: HealthRequirement
    actual_status: HealthStatus | None  # None = the check wasn't in the report at all


class ModuleHealthEvaluator:
    def is_satisfied(self, requirements: tuple[HealthRequirement, ...], report: HealthReport) -> bool:
        return len(self.unmet_requirements(requirements, report)) == 0

    def unmet_requirements(
        self, requirements: tuple[HealthRequirement, ...], report: HealthReport,
    ) -> tuple[UnmetHealthRequirement, ...]:
        by_name = {check.check_name: check.status for check in report.checks}
        unmet = []
        for requirement in requirements:
            actual = by_name.get(requirement.check_name)
            if actual is None or not is_at_least(actual, requirement.minimum_status):
                unmet.append(UnmetHealthRequirement(requirement=requirement, actual_status=actual))
        return tuple(unmet)
