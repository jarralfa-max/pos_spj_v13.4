"""ProductAuditEntry — the immutable audit record for every product mutation (§40).

Products is audit-ready: creation, edition, approval, activation, block, unblock,
deactivation, discontinuation, classification/unit/conversion/barcode/recipe/yield/
cutting/internal/assortment/import/matching/settings changes each build one of
these. It captures who, authorized-by, what, before/after, why, where and when.
Persistence lands with the products schema (PROD-4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.products.exceptions import InvalidAuthorizationError
from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class ProductAuditEntry:
    action: str
    entity_id: str
    user_id: str
    operation_id: str
    authorized_by: str | None = None
    before: dict | None = None
    after: dict | None = None
    reason: str | None = None
    branch_id: str | None = None
    source: str = "products"
    id: str = field(default_factory=new_uuid)
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        if not (self.action or "").strip():
            raise InvalidAuthorizationError("La auditoría requiere una acción")
        if not self.entity_id:
            raise InvalidAuthorizationError("La auditoría requiere entity_id")
        if not self.user_id:
            raise InvalidAuthorizationError("La auditoría requiere user_id")
        if not self.operation_id:
            raise InvalidAuthorizationError("La auditoría requiere operation_id")
