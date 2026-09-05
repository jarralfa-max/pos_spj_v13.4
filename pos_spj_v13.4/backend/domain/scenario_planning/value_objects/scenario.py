"""BusinessScenario / ScenarioVariable / ScenarioResult (§41-45, BI-19)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.exceptions import MissingScenarioVariableError
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class ScenarioVariable:
    kind: ScenarioVariableKind
    value: Decimal


@dataclass(frozen=True, slots=True)
class BusinessScenario:
    id: str
    name: str
    variables: tuple[ScenarioVariable, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.name:
            raise ValueError("BusinessScenario.name is required")
        if not self.variables:
            raise ValueError("BusinessScenario.variables must not be empty")
        kinds = [v.kind for v in self.variables]
        if len(kinds) != len(set(kinds)):
            raise ValueError("BusinessScenario.variables must not repeat a kind")

    def get(self, kind: ScenarioVariableKind) -> ScenarioVariable:
        for variable in self.variables:
            if variable.kind == kind:
                return variable
        raise MissingScenarioVariableError(
            f"BusinessScenario {self.name!r} has no variable of kind {kind.value}"
        )


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    baseline_metrics: dict[str, Decimal]
    scenario_metrics: dict[str, Decimal]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        validate_uuidv7(self.scenario_id)
        if not self.baseline_metrics:
            raise ValueError("ScenarioResult.baseline_metrics must not be empty")
        if set(self.baseline_metrics) != set(self.scenario_metrics):
            raise ValueError(
                "ScenarioResult.baseline_metrics and scenario_metrics must share the same keys"
            )

    def delta(self, key: str) -> Decimal:
        return self.scenario_metrics[key] - self.baseline_metrics[key]
