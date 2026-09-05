from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.exceptions import MissingScenarioVariableError
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioResult,
    ScenarioVariable,
)
from backend.shared.ids import new_uuid


def _scenario(**overrides) -> BusinessScenario:
    fields = dict(
        id=new_uuid(), name="Precio +10%",
        variables=(ScenarioVariable(kind=ScenarioVariableKind.PRICE_CHANGE_PCT,
                                     value=Decimal("10")),),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return BusinessScenario(**fields)


def test_valid_scenario_constructs():
    scenario = _scenario()
    variable = scenario.get(ScenarioVariableKind.PRICE_CHANGE_PCT)
    assert variable.value == Decimal("10")


def test_get_missing_variable_kind_raises():
    scenario = _scenario()
    with pytest.raises(MissingScenarioVariableError):
        scenario.get(ScenarioVariableKind.DEMAND_CHANGE_PCT)


def test_rejects_empty_variables():
    with pytest.raises(ValueError):
        _scenario(variables=())


def test_rejects_duplicate_variable_kind():
    with pytest.raises(ValueError):
        _scenario(variables=(
            ScenarioVariable(kind=ScenarioVariableKind.PRICE_CHANGE_PCT, value=Decimal("10")),
            ScenarioVariable(kind=ScenarioVariableKind.PRICE_CHANGE_PCT, value=Decimal("5")),
        ))


def test_rejects_empty_name():
    with pytest.raises(ValueError):
        _scenario(name="")


def test_scenario_result_delta():
    result = ScenarioResult(
        scenario_id=new_uuid(), baseline_metrics={"price": Decimal("100")},
        scenario_metrics={"price": Decimal("110")},
        evaluated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert result.delta("price") == Decimal("10")


def test_scenario_result_requires_matching_keys():
    with pytest.raises(ValueError):
        ScenarioResult(
            scenario_id=new_uuid(), baseline_metrics={"price": Decimal("100")},
            scenario_metrics={"other": Decimal("110")},
            evaluated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )


def test_scenario_result_rejects_empty_baseline():
    with pytest.raises(ValueError):
        ScenarioResult(
            scenario_id=new_uuid(), baseline_metrics={}, scenario_metrics={},
            evaluated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
