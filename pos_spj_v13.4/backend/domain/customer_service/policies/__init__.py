"""Domain policies for the Customer Service (atención al cliente) bounded
context (CRM-7)."""

from __future__ import annotations

from backend.domain.customer_service.policies.service_level_policy_resolver import (
    ServiceLevelPolicyResolver,
)

__all__ = ["ServiceLevelPolicyResolver"]
