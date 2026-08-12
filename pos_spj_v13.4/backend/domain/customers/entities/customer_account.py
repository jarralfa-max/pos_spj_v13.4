"""CustomerAccount — business account for CRM-managed enterprise customers (§13).

Mirrors backend/domain/suppliers/entities.py::SupplierContact's `.create()`
shape. A CustomerAccount groups a business customer's contacts under one
commercial entity; ``CustomerContactPerson`` links either to an account or
directly to an individual ``Customer``.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.customers.exceptions import InvalidCustomerStateError
from backend.shared.ids import new_uuid


@dataclass(slots=True)
class CustomerAccount:
    id: str
    customer_id: str
    account_type: str = "BUSINESS"
    industry: str = ""
    company_size: str = ""
    website: str = ""
    parent_account_id: str | None = None
    account_owner_user_id: str | None = None
    territory_id: str | None = None
    status: str = "ACTIVE"

    @classmethod
    def create(cls, customer_id: str, **kwargs) -> "CustomerAccount":
        if not customer_id:
            raise InvalidCustomerStateError("CustomerAccount requiere customer_id")
        return cls(id=new_uuid(), customer_id=customer_id, **kwargs)
