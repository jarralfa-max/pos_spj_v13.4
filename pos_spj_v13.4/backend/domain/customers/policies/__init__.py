"""Domain policies for the Customer Master bounded context (CRM-2+)."""

from __future__ import annotations

from backend.domain.customers.policies.duplicate_policy import (
    CustomerDuplicateMatch,
    CustomerDuplicatePolicy,
)
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)

__all__ = [
    "CustomerDuplicateMatch",
    "CustomerDuplicatePolicy",
    "CustomerSegregationOfDutiesPolicy",
]
