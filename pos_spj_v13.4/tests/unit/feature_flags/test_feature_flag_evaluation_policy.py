"""SET-21 — "Rules"/"Rollout": feature_flag_evaluation_policy.
resolve_flag_value. Pure domain — no DB.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.feature_flags.policies.feature_flag_evaluation_policy import resolve_flag_value
from backend.shared.ids import new_uuid


def _flag(**overrides) -> FeatureFlag:
    kwargs = dict(code="delivery_auto_asign", name="Auto-asignación de delivery", default_enabled=False)
    kwargs.update(overrides)
    return FeatureFlag.create(**kwargs)


def _rule(flag_id: str, scope_type: FeatureFlagScopeType, scope_id: str | None, **overrides) -> FeatureFlagRule:
    kwargs = dict(flag_id=flag_id, scope_type=scope_type, scope_id=scope_id, enabled=True)
    kwargs.update(overrides)
    return FeatureFlagRule.create(**kwargs)


class TestNoMatchingRuleFallsBackToDefault:
    def test_no_rules_returns_default_enabled(self):
        flag = _flag(default_enabled=False)
        assert resolve_flag_value(flag, []) is False

    def test_default_enabled_true_with_no_rules(self):
        flag = _flag(default_enabled=True)
        assert resolve_flag_value(flag, []) is True

    def test_rules_for_a_different_flag_are_ignored(self):
        flag = _flag()
        other_flag_rule = _rule(new_uuid(), FeatureFlagScopeType.GLOBAL, None, enabled=True)
        assert resolve_flag_value(flag, [other_flag_rule]) is flag.default_enabled

    def test_inactive_flag_always_returns_false_regardless_of_rules(self):
        flag = _flag(default_enabled=True)
        flag.deactivate()
        global_rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True)
        assert resolve_flag_value(flag, [global_rule]) is False


class TestSpecificityOrdering:
    def test_global_rule_applies_to_any_context(self):
        flag = _flag()
        global_rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True)
        assert resolve_flag_value(flag, [global_rule], branch_id=new_uuid()) is True
        assert resolve_flag_value(flag, [global_rule]) is True

    def test_branch_rule_beats_global_rule(self):
        flag = _flag()
        branch_id = new_uuid()
        global_rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True)
        branch_rule = _rule(flag.id, FeatureFlagScopeType.BRANCH, branch_id, enabled=False)
        assert resolve_flag_value(flag, [global_rule, branch_rule], branch_id=branch_id) is False
        # A different branch still gets the global rule.
        assert resolve_flag_value(flag, [global_rule, branch_rule], branch_id=new_uuid()) is True

    def test_user_rule_beats_branch_and_global_rules(self):
        flag = _flag()
        branch_id, user_id = new_uuid(), new_uuid()
        global_rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=False)
        branch_rule = _rule(flag.id, FeatureFlagScopeType.BRANCH, branch_id, enabled=False)
        user_rule = _rule(flag.id, FeatureFlagScopeType.USER, user_id, enabled=True)
        resolved = resolve_flag_value(
            flag, [global_rule, branch_rule, user_rule], branch_id=branch_id, user_id=user_id,
        )
        assert resolved is True


class TestRollout:
    def test_rollout_100_percent_is_always_on(self):
        flag = _flag()
        rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True, rollout_percentage=100)
        for key in ("a", "b", "c", "d", "e"):
            assert resolve_flag_value(flag, [rule], evaluation_key=key) is True

    def test_rollout_0_percent_is_always_off(self):
        flag = _flag()
        rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True, rollout_percentage=0)
        for key in ("a", "b", "c", "d", "e"):
            assert resolve_flag_value(flag, [rule], evaluation_key=key) is False

    def test_disabled_rule_ignores_rollout_percentage_entirely(self):
        flag = _flag()
        rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=False, rollout_percentage=100)
        assert resolve_flag_value(flag, [rule], evaluation_key="anyone") is False

    def test_same_evaluation_key_is_always_deterministic(self):
        flag = _flag()
        rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True, rollout_percentage=50)
        first = resolve_flag_value(flag, [rule], evaluation_key="user-42")
        second = resolve_flag_value(flag, [rule], evaluation_key="user-42")
        assert first == second

    def test_rollout_distribution_is_roughly_the_configured_percentage(self):
        flag = _flag()
        rule = _rule(flag.id, FeatureFlagScopeType.GLOBAL, None, enabled=True, rollout_percentage=30)
        results = [resolve_flag_value(flag, [rule], evaluation_key=f"key-{i}") for i in range(1000)]
        on_count = sum(results)
        # Deterministic hash bucketing — not exact, but must land in a
        # sane band around 30% for 1000 distinct keys.
        assert 200 <= on_count <= 400, on_count
