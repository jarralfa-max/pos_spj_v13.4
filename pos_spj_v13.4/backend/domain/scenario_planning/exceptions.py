"""Domain exceptions for the scenario_planning bounded context."""

from __future__ import annotations


class ScenarioPlanningDomainError(Exception):
    """Base for scenario_planning rule violations."""


class MissingScenarioVariableError(ScenarioPlanningDomainError):
    """Raised when a what-if service needs a variable kind the scenario
    doesn't define — never silently defaults a simulated change to zero."""


class InsufficientElasticityForSimulationError(ScenarioPlanningDomainError):
    """Raised when a pricing what-if is requested but the elasticity
    estimate has LOW confidence (§35) — simulating a volume/revenue impact
    from an elasticity that was never trusted enough to use for a real
    recommendation would be worse than not simulating at all."""
