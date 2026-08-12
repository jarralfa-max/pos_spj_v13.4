"""Domain policies for the Customer Privacy bounded context (CRM-9)."""

from __future__ import annotations

from backend.domain.customer_privacy.policies.data_retention_policy_resolver import (
    DataRetentionPolicyResolver,
)

__all__ = ["DataRetentionPolicyResolver"]
