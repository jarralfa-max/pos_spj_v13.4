"""ServiceLevelPolicyResolver — picks the applicable ServiceLevelPolicy for
a case without hardcoding one methodology (§30-32: "nunca hardcodeado").

Pure domain logic — no I/O. The caller loads all active policies from the
repository and passes them in; this only decides which one (if any)
applies, preferring the most specific match (most non-wildcard axes) —
same "caller supplies the config, policy only decides" split as
LeadQualificationPolicy/CRMStageTransitionPolicy.
"""

from __future__ import annotations

from backend.domain.customer_service.entities.service_level_policy import ServiceLevelPolicy
from backend.domain.customer_service.enums import ServiceCaseChannel, ServiceCasePriority, ServiceCaseType


class ServiceLevelPolicyResolver:
    def resolve(
        self, policies: list[ServiceLevelPolicy], *, case_type: ServiceCaseType,
        priority: ServiceCasePriority, origin_branch_id: str | None, channel: ServiceCaseChannel,
    ) -> ServiceLevelPolicy | None:
        candidates = [
            p for p in policies
            if p.active and p.matches(case_type=case_type, priority=priority,
                                      origin_branch_id=origin_branch_id, channel=channel)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.specificity())
