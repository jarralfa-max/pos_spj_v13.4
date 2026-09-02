"""Canonical enums for the Feature Flags bounded context — SET-21. See
docs/refactor/settings_legacy_inventory.md §6.3 — SET-0's own audit
already named this bounded context's target model
(`FeatureFlag`/`FeatureFlagRule`) and classified the legacy
`core/services/feature_flag_service.py`/`repositories/
feature_flag_repository.py` pair as "MOVE the evaluation logic (useful),
REWRITE the schema/repository, unifying it with the master prompt's
typed FeatureFlag/FeatureFlagRule".
"""

from __future__ import annotations

from enum import Enum


class FeatureFlagScopeType(str, Enum):
    """"Rules": how specific a `FeatureFlagRule` targets. Generalizes
    the legacy repository's own `branch_id IN (?, 0) ORDER BY branch_id
    DESC` precedence (a branch-specific row beats the `0`/global row)
    into an explicit specificity ranking, adding USER as a targeting
    dimension the legacy schema never had."""

    GLOBAL = "GLOBAL"
    BRANCH = "BRANCH"
    USER = "USER"


# Most specific first — the order `policies/feature_flag_evaluation_policy.py`
# uses to pick a rule when more than one could apply.
SCOPE_SPECIFICITY_ORDER: tuple[FeatureFlagScopeType, ...] = (
    FeatureFlagScopeType.USER, FeatureFlagScopeType.BRANCH, FeatureFlagScopeType.GLOBAL,
)


class FeatureFlagChangeStatus(str, Enum):
    """"Approval": lifecycle of one `FeatureFlagChangeRequest`."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"
