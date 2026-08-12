"""CustomerTaxProfile — fiscal master data for CFDI billing (§15).

One profile per customer (mirrors backend/domain/suppliers/entities.py::
SupplierCommercialTerms's one-per-supplier shape). Fiscal (CFDI issuance)
and Ventas (historical snapshots) are the entities that actually *use* this
data — this bounded context only owns the master record (§15: "Fiscal
administra CFDI. Clientes administra datos maestros. Ventas conserva
snapshots históricos.").
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.customers.enums import ValidationStatus
from backend.domain.customers.exceptions import InvalidCustomerStateError
from backend.shared.ids import new_uuid


@dataclass(slots=True)
class CustomerTaxProfile:
    id: str
    customer_id: str
    tax_identifier: str = ""
    legal_name: str = ""
    tax_regime: str = ""
    fiscal_postal_code: str = ""
    default_cfdi_use: str = ""
    billing_email: str | None = None
    validation_status: ValidationStatus = ValidationStatus.MANUAL
    validated_at: str | None = None

    @classmethod
    def create(cls, customer_id: str, **kwargs) -> "CustomerTaxProfile":
        if not customer_id:
            raise InvalidCustomerStateError("CustomerTaxProfile requiere customer_id")
        return cls(id=new_uuid(), customer_id=customer_id, **kwargs)
