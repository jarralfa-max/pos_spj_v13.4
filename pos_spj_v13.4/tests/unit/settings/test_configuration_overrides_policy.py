"""SET-4 — override_allowed enforcement (§9): a definition that forbids
overrides may only hold a value at its canonical scope
(default_scope, or GLOBAL). Pure domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import ConfigurationScopeNotAllowedError
from backend.domain.settings.policies.configuration_inheritance_policy import (
    assert_override_allowed,
    canonical_override_scope,
)


def _definition(**overrides) -> ConfigurationDefinition:
    kwargs = dict(
        key="finance.default_currency", module="finance", label="Moneda por defecto",
        value_type=ValueType.STRING,
        allowed_scopes={ScopeType.GLOBAL, ScopeType.COMPANY, ScopeType.BRANCH},
        default_value="MXN",
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


class TestCanonicalOverrideScope:
    def test_defaults_to_global_when_no_default_scope_set(self):
        definition = _definition()
        assert canonical_override_scope(definition) is ScopeType.GLOBAL

    def test_uses_definition_default_scope_when_set(self):
        definition = _definition(default_scope=ScopeType.COMPANY)
        assert canonical_override_scope(definition) is ScopeType.COMPANY


class TestAssertOverrideAllowed:
    def test_override_allowed_true_permits_any_allowed_scope(self):
        definition = _definition(override_allowed=True)
        assert_override_allowed(definition, ScopeType.BRANCH)
        assert_override_allowed(definition, ScopeType.GLOBAL)

    def test_override_allowed_false_permits_only_canonical_scope(self):
        definition = _definition(override_allowed=False)
        assert_override_allowed(definition, ScopeType.GLOBAL)  # canonical (no default_scope)
        with pytest.raises(ConfigurationScopeNotAllowedError):
            assert_override_allowed(definition, ScopeType.BRANCH)
        with pytest.raises(ConfigurationScopeNotAllowedError):
            assert_override_allowed(definition, ScopeType.COMPANY)

    def test_override_allowed_false_with_explicit_default_scope(self):
        definition = _definition(override_allowed=False, default_scope=ScopeType.COMPANY)
        assert_override_allowed(definition, ScopeType.COMPANY)  # canonical
        with pytest.raises(ConfigurationScopeNotAllowedError):
            assert_override_allowed(definition, ScopeType.GLOBAL)
        with pytest.raises(ConfigurationScopeNotAllowedError):
            assert_override_allowed(definition, ScopeType.BRANCH)

    def test_is_independent_of_inheritance_enabled(self):
        # override_allowed gates *where a value may be written*;
        # inheritance_enabled gates *how resolution falls back at read
        # time*. A definition can disable one without the other.
        definition = _definition(override_allowed=False, inheritance_enabled=False)
        assert_override_allowed(definition, ScopeType.GLOBAL)
        with pytest.raises(ConfigurationScopeNotAllowedError):
            assert_override_allowed(definition, ScopeType.BRANCH)
