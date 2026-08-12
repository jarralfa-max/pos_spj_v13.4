"""Value objects for the CRM (relationship) bounded context (CRM-4+)."""

from __future__ import annotations

from backend.domain.crm.value_objects.lead_code import LeadCode
from backend.domain.crm.value_objects.opportunity_code import OpportunityCode

__all__ = ["LeadCode", "OpportunityCode"]
