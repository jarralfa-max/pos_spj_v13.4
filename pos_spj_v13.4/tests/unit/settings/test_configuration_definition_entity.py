"""SET-2 — ConfigurationDefinition entity. Pure domain — no DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.shared.ids import is_uuidv7


def _definition(**overrides) -> ConfigurationDefinition:
    kwargs = dict(
        key="orders.weight_adjustment_tolerance_pct", module="orders",
        label="Tolerancia de peso", value_type=ValueType.PERCENT,
        allowed_scopes={ScopeType.GLOBAL, ScopeType.BRANCH},
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7(self):
        definition = _definition()
        assert is_uuidv7(definition.id)

    def test_requires_module_and_label(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(module="   ")
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(label="")

    def test_requires_at_least_one_allowed_scope(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(allowed_scopes=set())

    def test_default_scope_must_be_within_allowed_scopes(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(default_scope=ScopeType.WORKSTATION)
        definition = _definition(default_scope=ScopeType.BRANCH)
        assert definition.default_scope is ScopeType.BRANCH

    def test_enum_requires_allowed_values(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(value_type=ValueType.ENUM, default_value=None)

    def test_default_value_is_type_checked(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(default_value=5.0)  # PERCENT requires Decimal, not float
        definition = _definition(default_value=Decimal("5.00"))
        assert definition.default_value == Decimal("5.00")

    def test_default_value_is_checked_against_allowed_values(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _definition(
                value_type=ValueType.ENUM, allowed_values=("A", "B"), default_value="C",
            )
        definition = _definition(
            value_type=ValueType.ENUM, allowed_values=("A", "B"), default_value="A",
        )
        assert definition.default_value == "A"

    def test_key_is_normalized_via_configuration_key(self):
        definition = _definition()
        assert str(definition.key) == "orders.weight_adjustment_tolerance_pct"
        assert definition.key.module == "orders"


class TestBehavior:
    def test_allows_scope(self):
        definition = _definition()
        assert definition.allows_scope(ScopeType.BRANCH)
        assert not definition.allows_scope(ScopeType.WORKSTATION)

    def test_deprecate_sets_flag_and_replacement(self):
        definition = _definition()
        definition.deprecate(replacement_key="orders.weight_tolerance_v2")
        assert definition.deprecated is True
        assert definition.replacement_key == "orders.weight_tolerance_v2"

    def test_deprecate_twice_raises(self):
        definition = _definition()
        definition.deprecate()
        with pytest.raises(ConfigurationInvalidValueError):
            definition.deprecate()
