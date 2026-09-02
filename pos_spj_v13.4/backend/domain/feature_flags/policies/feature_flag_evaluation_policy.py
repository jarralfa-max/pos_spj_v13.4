"""FeatureFlagEvaluationPolicy — SET-21 "Rules"/"Rollout": what
`is_enabled()` should actually return, generalizing
`core/services/feature_flag_service.py::FeatureFlagService.is_enabled()`
(which only ever looks up a per-branch bool, no rollout).

Resolution order: the most specific *matching* active rule wins (USER >
BRANCH > GLOBAL — `enums.SCOPE_SPECIFICITY_ORDER`), the same "most
specific match wins" principle
`backend.domain.settings.services.configuration_resolution_service` and
`backend.domain.device_management.policies.print_routing_policy` already
established, independently reimplemented here (bounded-context
independence). No matching rule falls back to `flag.default_enabled` —
the same "unknown flag defaults to off" safety net the legacy service
already had, just now driven by explicit per-flag data instead of one
hardcoded assumption.

`rollout_percentage < 100` on the winning rule uses a deterministic hash
of `(flag.code, evaluation_key)` so the same key always lands on the same
side of the rollout — no randomness, reproducible in tests.
"""

from __future__ import annotations

import hashlib

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import SCOPE_SPECIFICITY_ORDER, FeatureFlagScopeType


def _in_rollout(*, flag_code: str, evaluation_key: str, percentage: int) -> bool:
    if percentage >= 100:
        return True
    if percentage <= 0:
        return False
    digest = hashlib.sha256(f"{flag_code}:{evaluation_key}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < percentage


def resolve_flag_value(
    flag: FeatureFlag, rules: list[FeatureFlagRule], *, branch_id: str | None = None,
    user_id: str | None = None, evaluation_key: str = "",
) -> bool:
    if not flag.active:
        return False

    candidates_by_scope = {
        FeatureFlagScopeType.USER: user_id, FeatureFlagScopeType.BRANCH: branch_id,
        FeatureFlagScopeType.GLOBAL: None,
    }
    for scope_type in SCOPE_SPECIFICITY_ORDER:
        scope_id = candidates_by_scope[scope_type]
        if scope_type is not FeatureFlagScopeType.GLOBAL and scope_id is None:
            continue
        for rule in rules:
            if rule.flag_id != flag.id or not rule.matches(scope_type, scope_id):
                continue
            if not rule.enabled:
                return False
            return _in_rollout(
                flag_code=flag.code, evaluation_key=evaluation_key or scope_id or "",
                percentage=rule.rollout_percentage,
            )

    return flag.default_enabled
