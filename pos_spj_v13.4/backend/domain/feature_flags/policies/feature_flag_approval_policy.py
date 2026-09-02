"""FeatureFlagApprovalPolicy — SET-21 "Approval": segregation of duties
for `FeatureFlagChangeRequest` — the same §59 rule
`backend.domain.settings.policies.configuration_approval_policy.
assert_can_approve` already enforces for configuration changes,
independently reimplemented here.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.exceptions import FeatureFlagApprovalRequiredError


def assert_can_approve(request: FeatureFlagChangeRequest, *, approver_user_id: str) -> None:
    if request.requested_by_user_id == approver_user_id:
        raise FeatureFlagApprovalRequiredError(
            "Quien solicita un cambio de feature flag no puede aprobarlo — se requiere un "
            "segundo usuario (segregación de funciones, §59)."
        )
