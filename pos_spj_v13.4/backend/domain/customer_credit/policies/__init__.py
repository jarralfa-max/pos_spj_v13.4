"""Domain policies for the Customer Credit bounded context (CRM-8)."""

from __future__ import annotations

from backend.domain.customer_credit.policies.credit_sale_eligibility_policy import (
    CreditSaleEligibilityPolicy,
)

__all__ = ["CreditSaleEligibilityPolicy"]
