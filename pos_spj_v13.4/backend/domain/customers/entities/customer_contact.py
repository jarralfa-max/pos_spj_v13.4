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
from backend.domain.customers.value_objects.email_address import EmailAddress
from backend.domain.customers.value_objects.phone_number import PhoneNumber
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
        kwargs["phone_e164"] = normalize_phone(kwargs.get("phone_e164"))
        kwargs["email"] = normalize_email(kwargs.get("email"))
        return cls(id=new_uuid(), customer_id=customer_id, first_name=first_name.strip(),
                   **kwargs)

    def update(self, *, first_name: str | None = None, last_name: str | None = None,
               job_title: str | None = None, department: str | None = None,
               phone_e164: str | None = None, email: str | None = None,
               decision_role=None) -> None:
        """Auditoría CRM F14: la edición aplica las MISMAS reglas que el alta
        (nombre obligatorio, teléfono E.164, correo válido). Antes asignaba los
        atributos directo y aceptaba nombre vacío y teléfono/correo inválidos.
        ``""`` en teléfono o correo los borra; ``None`` deja el valor."""
        if first_name is not None:
            if not first_name.strip():
                raise InvalidCustomerStateError("El contacto requiere nombre")
            self.first_name = first_name.strip()
        if last_name is not None:
            self.last_name = last_name.strip()
        if job_title is not None:
            self.job_title = job_title
        if department is not None:
            self.department = department
        if phone_e164 is not None:
            self.phone_e164 = normalize_phone(phone_e164)
        if email is not None:
            self.email = normalize_email(email)
        if decision_role is not None:
            self.decision_role = ContactDecisionRole(decision_role)


def normalize_phone(value: str | None) -> str | None:
    """E.164 o ``None``; un valor inválido es error, nunca se guarda tal cual."""
    if value is None or not str(value).strip():
        return None
    return PhoneNumber(str(value)).value


def normalize_email(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return EmailAddress(str(value)).value
