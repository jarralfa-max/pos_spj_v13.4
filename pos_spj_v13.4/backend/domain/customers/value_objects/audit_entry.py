"""CustomerAuditEntry — the immutable audit record for every CRM mutation (§76).

Broader than the legacy `audit_write()` helper (core/services/auto_audit.py):
the master prompt requires `correlation_id` and `workstation_id` in addition
to who/what/before/after/why/where/when. `audit_write()` remains the sink
legacy code calls; use cases built on this bounded context build one of these
records and pass it to whatever persists it (CRM-3+ wires the repository —
this value object only encodes the shape and its invariants). Mirrors
backend/domain/products/value_objects/product_audit_entry.py, extended per
§76's field list (customer_id, workstation_id, correlation_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customers.exceptions import InvalidAuthorizationError
from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class CustomerAuditEntry:
    action: str
    entity_type: str
    entity_id: str
    user_id: str
    operation_id: str
    authorized_by: str | None = None
    customer_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    reason: str | None = None
    branch_id: str | None = None
    workstation_id: str | None = None
    correlation_id: str | None = None
    source: str = "customers_crm"
    id: str = field(default_factory=new_uuid)
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        if not (self.action or "").strip():
            raise InvalidAuthorizationError("La auditoría requiere una acción")
        if not (self.entity_type or "").strip():
            raise InvalidAuthorizationError("La auditoría requiere entity_type")
        if not self.entity_id:
            raise InvalidAuthorizationError("La auditoría requiere entity_id")
        if not self.user_id:
            raise InvalidAuthorizationError("La auditoría requiere user_id")
        if not self.operation_id:
            raise InvalidAuthorizationError("La auditoría requiere operation_id")
