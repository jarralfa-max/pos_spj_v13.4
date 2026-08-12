"""CustomerDataRetentionPolicy (§44): "configurable por empresa/tipo de
cliente/tipo de dato/estado/obligación legal; plazos nunca hardcodeados."
Data, not a hardcoded constant — mirrors CRM-5's CRMStageDefinition/CRM-7's
ServiceLevelPolicy: wildcard-matching axes, most-specific-wins resolution
via ``DataRetentionPolicyResolver``.

"Por empresa" (multi-company) has no existing axis anywhere else in this
module (this codebase's multi-tenancy model, if any, lives outside CRM) —
not modeled here; every policy implicitly applies company-wide. The other
three named axes (customer_type, data_category, customer_status) are
modeled as wildcard-or-value fields, same as ServiceLevelPolicy's
case_type/priority/channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_privacy.exceptions import InvalidDataRetentionPolicyError
from backend.domain.customers.enums import CustomerStatus, CustomerType
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CustomerDataRetentionPolicy:
    id: str
    code: str
    name: str
    data_category: str
    retention_days: int
    legal_basis: str = ""
    customer_type: CustomerType | None = None
    customer_status: CustomerStatus | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: str, name: str, data_category: str, retention_days: int, *,
        legal_basis: str = "", customer_type: CustomerType | None = None,
        customer_status: CustomerStatus | None = None,
    ) -> "CustomerDataRetentionPolicy":
        if not code or not code.strip():
            raise InvalidDataRetentionPolicyError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidDataRetentionPolicyError("name es obligatorio")
        if not data_category or not data_category.strip():
            raise InvalidDataRetentionPolicyError("data_category es obligatorio")
        if retention_days <= 0:
            raise InvalidDataRetentionPolicyError("retention_days debe ser positivo")
        return cls(
            id=new_uuid(), code=code.strip().upper(), name=name.strip(),
            data_category=data_category.strip().upper(), retention_days=retention_days,
            legal_basis=legal_basis, customer_type=customer_type,
            customer_status=customer_status,
        )

    def matches(
        self, *, data_category: str, customer_type: CustomerType | None = None,
        customer_status: CustomerStatus | None = None,
    ) -> bool:
        return (
            self.data_category == data_category.strip().upper()
            and (self.customer_type is None or self.customer_type == customer_type)
            and (self.customer_status is None or self.customer_status == customer_status)
        )

    def specificity(self) -> int:
        return sum(1 for axis in (self.customer_type, self.customer_status) if axis is not None)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
