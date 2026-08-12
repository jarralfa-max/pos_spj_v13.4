"""CustomerContactPerson — a contact for a business account or an individual
customer (§13). Mirrors backend/domain/suppliers/entities.py::SupplierContact.

Never confuse this with the *customer* who is a person (§13): a contact is
always someone acting on behalf of an account (or, for an individual
customer with no account, an alternate point of contact).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.customers.enums import ContactDecisionRole
from backend.domain.customers.exceptions import InvalidCustomerStateError
from backend.shared.ids import new_uuid


@dataclass(slots=True)
class CustomerContactPerson:
    id: str
    customer_id: str
    first_name: str
    last_name: str = ""
    customer_account_id: str | None = None
    job_title: str = ""
    department: str = ""
    phone_e164: str | None = None
    email: str | None = None
    decision_role: ContactDecisionRole = ContactDecisionRole.OTHER
    is_primary: bool = False
    status: str = "ACTIVE"

    @classmethod
    def create(cls, customer_id: str, first_name: str, **kwargs) -> "CustomerContactPerson":
        if not customer_id:
            raise InvalidCustomerStateError("CustomerContactPerson requiere customer_id")
        if not first_name or not first_name.strip():
            raise InvalidCustomerStateError("El contacto requiere nombre")
        return cls(id=new_uuid(), customer_id=customer_id, first_name=first_name.strip(),
                   **kwargs)
