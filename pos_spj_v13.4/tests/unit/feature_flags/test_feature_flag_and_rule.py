"""SET-21 — "Flags"/"Rules"/"Rollout": FeatureFlag + FeatureFlagRule
entities. Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import FeatureFlagsInvalidValueError
from backend.shared.ids import is_uuidv7, new_uuid


def _flag(**overrides) -> FeatureFlag:
    kwargs = dict(code="delivery_auto_asign", name="Auto-asignación de delivery")
    kwargs.update(overrides)
    return FeatureFlag.create(**kwargs)


class TestFeatureFlagCreate:
    def test_mints_uuidv7_and_defaults(self):
        flag = _flag()
        assert is_uuidv7(flag.id)
        assert flag.default_enabled is False
        assert flag.active is True

    def test_requires_code(self):
        with pytest.raises(FeatureFlagsInvalidValueError):
            _flag(code="   ")

    def test_requires_name(self):
        with pytest.raises(FeatureFlagsInvalidValueError):
            _flag(name="   ")

    def test_activate_deactivate(self):
        flag = _flag()
        flag.deactivate()
        assert flag.active is False
        flag.activate()
        assert flag.active is True


class TestFeatureFlagUpdateDetails:
    def test_updates_fields_and_bumps_updated_at(self):
        flag = _flag()
        original_updated_at = flag.updated_at
        flag.update_details(name="Nuevo nombre", description="desc", default_enabled=True)
        assert flag.name == "Nuevo nombre"
        assert flag.description == "desc"
        assert flag.default_enabled is True
        assert flag.updated_at >= original_updated_at

    def test_rejects_blank_name(self):
        flag = _flag()
        with pytest.raises(FeatureFlagsInvalidValueError):
            flag.update_details(name="   ")

    def test_does_not_touch_code_or_id(self):
        flag = _flag()
        original_code, original_id = flag.code, flag.id
        flag.update_details(name="Otro nombre")
        assert flag.code == original_code
        assert flag.id == original_id


class TestFeatureFlagRuleCreate:
    def test_mints_uuidv7(self):
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        assert is_uuidv7(rule.id)
        assert rule.rollout_percentage == 100
        assert rule.active is True

    def test_global_scope_rejects_scope_id(self):
        with pytest.raises(FeatureFlagsInvalidValueError):
            FeatureFlagRule.create(
                flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=new_uuid(),
                enabled=True,
            )

    @pytest.mark.parametrize("scope_type", [FeatureFlagScopeType.BRANCH, FeatureFlagScopeType.USER])
    def test_non_global_scope_requires_scope_id(self, scope_type):
        with pytest.raises(FeatureFlagsInvalidValueError):
            FeatureFlagRule.create(flag_id=new_uuid(), scope_type=scope_type, scope_id=None, enabled=True)

    @pytest.mark.parametrize("percentage", [-1, 101, 1.5, True])
    def test_rejects_invalid_rollout_percentage(self, percentage):
        with pytest.raises(FeatureFlagsInvalidValueError):
            FeatureFlagRule.create(
                flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
                rollout_percentage=percentage,
            )

    def test_activate_deactivate(self):
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        rule.deactivate()
        assert rule.active is False
        rule.activate()
        assert rule.active is True


class TestFeatureFlagRuleMatches:
    def test_matches_same_scope_when_active(self):
        branch_id = new_uuid()
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.BRANCH, scope_id=branch_id, enabled=True,
        )
        assert rule.matches(FeatureFlagScopeType.BRANCH, branch_id) is True

    def test_does_not_match_different_scope_id(self):
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.BRANCH, scope_id=new_uuid(), enabled=True,
        )
        assert rule.matches(FeatureFlagScopeType.BRANCH, new_uuid()) is False

    def test_does_not_match_different_scope_type(self):
        branch_id = new_uuid()
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.BRANCH, scope_id=branch_id, enabled=True,
        )
        assert rule.matches(FeatureFlagScopeType.USER, branch_id) is False

    def test_inactive_rule_never_matches(self):
        rule = FeatureFlagRule.create(
            flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        rule.deactivate()
        assert rule.matches(FeatureFlagScopeType.GLOBAL, None) is False
