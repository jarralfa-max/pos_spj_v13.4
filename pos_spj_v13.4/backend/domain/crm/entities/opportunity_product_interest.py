"""OpportunityProductInterest — a product/service line the customer showed
interest in during a deal (§19-22). ``product_reference_id`` is an opaque
pointer into the Productos bounded context (never a foreign key across
schema files — CRM does not own the product catalog, same loose-coupling
choice as ``Lead.origin_branch_id``/``territory_id``); ``product_name`` is a
denormalized snapshot so the interest line still reads correctly even if the
referenced product is later renamed or removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.crm.exceptions import CRMDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value) -> Decimal:
    if value is None:
        raise CRMDomainError("quantity es obligatorio")
    if isinstance(value, bool) or isinstance(value, float):
        raise CRMDomainError("quantity debe ser Decimal, nunca float")
    return Decimal(str(value))


def _opt_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise CRMDomainError("estimated_unit_price debe ser Decimal, nunca float")
    return Decimal(str(value))


@dataclass(slots=True)
class OpportunityProductInterest:
    id: str
    opportunity_id: str
    product_name: str
    quantity: Decimal
    product_reference_id: str | None = None
    estimated_unit_price: Decimal | None = None
    notes: str = ""
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, opportunity_id: str, product_name: str, *, quantity=Decimal("1"),
        product_reference_id: str | None = None, estimated_unit_price=None, notes: str = "",
    ) -> "OpportunityProductInterest":
        if not opportunity_id:
            raise CRMDomainError("OpportunityProductInterest requiere opportunity_id")
        if not product_name or not product_name.strip():
            raise CRMDomainError("product_name es obligatorio")
        qty = _decimal(quantity)
        if qty <= 0:
            raise CRMDomainError("quantity debe ser mayor a cero")
        return cls(
            id=new_uuid(), opportunity_id=opportunity_id, product_name=product_name.strip(),
            quantity=qty, product_reference_id=product_reference_id,
            estimated_unit_price=_opt_decimal(estimated_unit_price), notes=notes,
        )
