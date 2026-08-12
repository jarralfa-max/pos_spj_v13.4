"""Value objects for the Customer Master bounded context (CRM-2+)."""

from __future__ import annotations

from backend.domain.customers.value_objects.customer_code import CustomerCode
from backend.domain.customers.value_objects.email_address import EmailAddress
from backend.domain.customers.value_objects.phone_number import PhoneNumber

__all__ = ["CustomerCode", "EmailAddress", "PhoneNumber"]
