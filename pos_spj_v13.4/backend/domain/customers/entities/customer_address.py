"""CustomerAddress — a customer's postal address (§14). Mirrors
backend/domain/suppliers/entities.py::SupplierAddress, extended with the
Mexican address decomposition (external/internal number, colonia,
municipio) §14 asks for instead of a single free-text ``line``.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.customers.enums import AddressType, ValidationStatus
from backend.domain.customers.exceptions import InvalidCustomerStateError
from backend.shared.ids import new_uuid


@dataclass(slots=True)
class CustomerAddress:
    id: str
    customer_id: str
    address_type: AddressType
    street: str
    external_number: str = ""
    internal_number: str = ""
    neighborhood: str = ""
    postal_code: str = ""
    locality: str = ""
    municipality: str = ""
    state: str = ""
    country: str = "MX"
    references: str = ""
    latitude: float | None = None
    longitude: float | None = None
    validation_status: ValidationStatus = ValidationStatus.MANUAL
    is_default: bool = False

    @classmethod
    def create(cls, customer_id: str, address_type: AddressType, street: str,
               **kwargs) -> "CustomerAddress":
        if not customer_id:
            raise InvalidCustomerStateError("CustomerAddress requiere customer_id")
        if not street or not street.strip():
            raise InvalidCustomerStateError("La dirección requiere calle")
        return cls(id=new_uuid(), customer_id=customer_id, address_type=address_type,
                   street=street.strip(), **kwargs)
