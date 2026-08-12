"""DataRetentionPolicyResolver — picks the applicable
CustomerDataRetentionPolicy without hardcoding one retention schedule
(§44: "plazos nunca hardcodeados"). Pure domain logic — no I/O. Mirrors
CRM-7's ServiceLevelPolicyResolver exactly: caller loads all active
policies, this only decides which one (if any) applies, preferring the
most specific match.
"""

from __future__ import annotations

from backend.domain.customer_privacy.entities.customer_data_retention_policy import (
    CustomerDataRetentionPolicy,
)
from backend.domain.customers.enums import CustomerStatus, CustomerType


class DataRetentionPolicyResolver:
    def resolve(
        self, policies: list[CustomerDataRetentionPolicy], *, data_category: str,
        customer_type: CustomerType | None = None, customer_status: CustomerStatus | None = None,
    ) -> CustomerDataRetentionPolicy | None:
        candidates = [
            p for p in policies
            if p.active and p.matches(data_category=data_category, customer_type=customer_type,
                                      customer_status=customer_status)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.specificity())
