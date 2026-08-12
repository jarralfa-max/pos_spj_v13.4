"""Domain policies for the CRM (relationship) bounded context (CRM-4+)."""

from __future__ import annotations

from backend.domain.crm.policies.duplicate_policy import LeadDuplicateMatch, LeadDuplicatePolicy
from backend.domain.crm.policies.qualification_policy import LeadQualificationPolicy
from backend.domain.crm.policies.stage_transition_policy import CRMStageTransitionPolicy

__all__ = [
    "LeadDuplicateMatch", "LeadDuplicatePolicy", "LeadQualificationPolicy",
    "CRMStageTransitionPolicy",
]
