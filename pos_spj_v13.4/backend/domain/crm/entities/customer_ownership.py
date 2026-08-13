"""CustomerOwnership — one evidence record of an ownership assignment
(§33-36: "con historial de asignación — no solo vendedor_id plano"). Mirrors
backend/domain/customer_privacy/entities/customer_consent.py's append-only
shape: assigning/reassigning an owner never overwrites a row, it captures a
new one, so the full history of who owned a customer account (and for which
OwnershipType) is always reconstructable. The "current" owner for a given
(customer_id, ownership_type) is resolved via
CustomerOwnershipRepositoryPort.get_latest() — nothing here is ever mutated
in place.

Only OwnershipType.PRIMARY is kept in sync with the denormalized
Customer.account_owner_user_id fast-path field — see
backend/application/crm/use_cases/ownership_use_cases.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import OwnershipType
from backend.domain.crm.exceptions import InvalidCustomerOwnershipError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerOwnership:
    id: str
    customer_id: str
    ownership_type: OwnershipType
    owner_user_id: str
    assigned_by_user_id: str | None = None
    reason: str = ""
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def capture(
        cls, customer_id: str, ownership_type: OwnershipType, owner_user_id: str, *,
        assigned_by_user_id: str | None = None, reason: str = "",
        operation_id: str | None = None,
    ) -> "CustomerOwnership":
        if not customer_id:
            raise InvalidCustomerOwnershipError("customer_id es obligatorio")
        if not owner_user_id:
            raise InvalidCustomerOwnershipError("owner_user_id es obligatorio")
        return cls(
            id=new_uuid(), customer_id=customer_id, ownership_type=ownership_type,
            owner_user_id=owner_user_id, assigned_by_user_id=assigned_by_user_id,
            reason=reason.strip(), operation_id=operation_id,
        )
