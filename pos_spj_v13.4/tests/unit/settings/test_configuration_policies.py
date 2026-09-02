"""SET-2 — Settings policies: validation, inheritance, approval,
activation, rollback, sensitive. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.entities.configuration_definition import ConfigurationDefinition
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.enums import ScopeType, ValueType
from backend.domain.settings.exceptions import (
    ConfigurationActivationNotAllowedError,
    ConfigurationApprovalRequiredError,
    ConfigurationInvalidValueError,
    ConfigurationRollbackNotAllowedError,
    ConfigurationScopeNotAllowedError,
    SensitiveConfigurationAccessDeniedError,
)
from backend.domain.settings.policies import (
    configuration_activation_policy,
    configuration_approval_policy,
    configuration_inheritance_policy,
    configuration_rollback_policy,
    sensitive_configuration_policy,
)
from backend.domain.settings.policies.configuration_validation_policy import (
    validate_against_definition,
    validate_schema_constraints,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.shared.ids import new_uuid

_NOW = datetime.now(timezone.utc)


def _definition(**overrides) -> ConfigurationDefinition:
    kwargs = dict(
        key="orders.weight_adjustment_tolerance_pct", module="orders",
        label="Tolerancia de peso", value_type=ValueType.PERCENT,
        allowed_scopes={ScopeType.GLOBAL, ScopeType.BRANCH, ScopeType.WORKSTATION},
    )
    kwargs.update(overrides)
    return ConfigurationDefinition.create(**kwargs)


def _value(definition, *, created_by_user_id="creator-1", **overrides) -> ConfigurationValue:
    kwargs = dict(
        definition_id=definition.id,
        scope=ConfigurationScope.create(ScopeType.BRANCH, new_uuid()),
        value=Decimal("7.5"),
        effective_period=EffectivePeriod.create(_NOW - timedelta(days=1)),
        created_by_user_id=created_by_user_id,
    )
    kwargs.update(overrides)
    return ConfigurationValue.create(**kwargs)


class TestConfigurationValidationPolicy:
    def test_validate_against_definition_checks_type_and_allowed_values(self):
        definition = _definition(
            value_type=ValueType.ENUM, allowed_values=("A", "B"),
            allowed_scopes={ScopeType.GLOBAL},
        )
        validate_against_definition(definition, "A")
        with pytest.raises(ConfigurationInvalidValueError):
            validate_against_definition(definition, "C")

    def test_schema_constraints_min_max(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.INTEGER, 1, {"min": 5})
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.INTEGER, 10, {"max": 5})
        validate_schema_constraints(ValueType.INTEGER, 7, {"min": 5, "max": 10})

    def test_schema_constraints_decimal_min_coerces_int_literal(self):
        # min/max in validation_schema may be written as plain ints/JSON
        # numbers even for DECIMAL/MONEY/PERCENT fields — the policy
        # coerces them so callers don't have to pre-Decimal their schema.
        validate_schema_constraints(ValueType.PERCENT, Decimal("7.5"), {"min": 0, "max": 100})
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.PERCENT, Decimal("7.5"), {"max": 5})

    def test_schema_constraints_string_length_and_pattern(self):
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.STRING, "ab", {"min_length": 3})
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.STRING, "abcdef", {"max_length": 3})
        with pytest.raises(ConfigurationInvalidValueError):
            validate_schema_constraints(ValueType.STRING, "abc", {"pattern": r"\d+"})
        validate_schema_constraints(ValueType.STRING, "123", {"pattern": r"\d+"})


class TestConfigurationInheritancePolicy:
    def test_assert_scope_allowed_raises_for_disallowed_scope(self):
        definition = _definition()
        with pytest.raises(ConfigurationScopeNotAllowedError):
            configuration_inheritance_policy.assert_scope_allowed(definition, ScopeType.PRODUCT)

    def test_resolution_order_is_most_specific_first_and_restricted(self):
        definition = _definition()
        order = configuration_inheritance_policy.resolution_order(definition)
        assert order == (ScopeType.WORKSTATION, ScopeType.BRANCH, ScopeType.GLOBAL)

    def test_resolution_order_without_inheritance_is_default_scope_only(self):
        definition = _definition(inheritance_enabled=False, default_scope=ScopeType.BRANCH)
        assert configuration_inheritance_policy.resolution_order(definition) == (ScopeType.BRANCH,)


class TestConfigurationApprovalPolicy:
    def test_requires_approval_reflects_definition_flag(self):
        assert configuration_approval_policy.requires_approval(_definition(approval_required=True))
        assert not configuration_approval_policy.requires_approval(_definition(approval_required=False))

    def test_creator_cannot_approve_own_change(self):
        definition = _definition()
        value = _value(definition, created_by_user_id="u1")
        with pytest.raises(ConfigurationApprovalRequiredError):
            configuration_approval_policy.assert_can_approve(value, approver_user_id="u1")
        configuration_approval_policy.assert_can_approve(value, approver_user_id="u2")


class TestConfigurationActivationPolicy:
    def test_approver_cannot_activate_critical_change_alone(self):
        definition = _definition(approval_required=True)
        value = _value(definition, created_by_user_id="u1")
        value.submit_for_approval()
        value.approve("u2")
        with pytest.raises(ConfigurationActivationNotAllowedError):
            configuration_activation_policy.assert_can_activate(definition, value, activator_user_id="u2")
        configuration_activation_policy.assert_can_activate(definition, value, activator_user_id="u3")

    def test_non_critical_change_has_no_activator_restriction(self):
        definition = _definition(approval_required=False)
        value = _value(definition, created_by_user_id="u1")
        value.auto_approve("u1")
        configuration_activation_policy.assert_can_activate(definition, value, activator_user_id="u1")

    def test_activation_requires_restart_flag(self):
        assert configuration_activation_policy.activation_requires_restart(_definition(restart_required=True))
        assert not configuration_activation_policy.activation_requires_restart(_definition(restart_required=False))


class TestConfigurationRollbackPolicy:
    def test_only_active_or_expired_may_roll_back(self):
        definition = _definition()
        draft_value = _value(definition)
        with pytest.raises(ConfigurationRollbackNotAllowedError):
            configuration_rollback_policy.assert_can_roll_back(draft_value)

    def test_build_rollback_draft_marks_current_rolled_back_and_chains_new_draft(self):
        definition = _definition()
        old_value = _value(
            definition, value=Decimal("5.0"),
            effective_period=EffectivePeriod.create(
                _NOW - timedelta(days=10), _NOW - timedelta(days=5),
            ),
        )
        old_value.auto_approve("u1")
        old_value.activate("u1", at=_NOW - timedelta(days=9))
        old_value.expire(at=_NOW - timedelta(hours=1))

        current_value = _value(definition, value=Decimal("7.5"))
        current_value.auto_approve("u1")
        current_value.activate("u1", at=_NOW - timedelta(hours=1))

        draft = configuration_rollback_policy.build_rollback_draft(
            current_value, old_value, effective_period=EffectivePeriod.create(_NOW),
            requested_by_user_id="u9", reason="revertir cambio erróneo",
        )
        assert current_value.status.value == "ROLLED_BACK"
        assert draft.value == Decimal("5.0")
        assert draft.previous_version_id == current_value.id
        assert draft.reason == "revertir cambio erróneo"

    def test_build_rollback_draft_requires_reason(self):
        definition = _definition()
        old_value = _value(definition)
        current_value = _value(definition)
        current_value.auto_approve("u1")
        current_value.activate("u1", at=_NOW)
        with pytest.raises(ConfigurationInvalidValueError):
            configuration_rollback_policy.build_rollback_draft(
                current_value, old_value, effective_period=EffectivePeriod.create(_NOW),
                requested_by_user_id="u9", reason="   ",
            )


class TestSensitiveConfigurationPolicy:
    def test_non_sensitive_definition_never_masks(self):
        definition = _definition(sensitive=False)
        assert sensitive_configuration_policy.mask_for_display(definition, Decimal("7.5")) == Decimal("7.5")
        sensitive_configuration_policy.assert_can_view_raw(definition, has_sensitive_access=False)

    def test_sensitive_definition_masks_and_gates_access(self):
        definition = _definition(sensitive=True, value_type=ValueType.SECRET_REFERENCE, allowed_scopes={ScopeType.GLOBAL})
        assert sensitive_configuration_policy.mask_for_display(definition, "wa_meta_token") == "••••••"
        with pytest.raises(SensitiveConfigurationAccessDeniedError):
            sensitive_configuration_policy.assert_can_view_raw(definition, has_sensitive_access=False)
        sensitive_configuration_policy.assert_can_view_raw(definition, has_sensitive_access=True)
