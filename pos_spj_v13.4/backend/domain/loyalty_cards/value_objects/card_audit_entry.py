"""CardAuditEntry — one auditable Loyalty Cards action (master prompt §61:
tarjetas, QR, plantillas, lotes, impresión, reimpresión, reposición,
bloqueo).

Pure value object; persistence is ``backend/application/loyalty_cards/audit.py``.
Mirrors ``backend/domain/sales/value_objects/sales_audit_entry.py`` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.loyalty_cards.exceptions import InvalidLoyaltyCardAuditFieldError


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CardAuditEntry:
    user_id: str
    operation_id: str
    action: str
    branch_id: str
    authorized_by: str | None = None
    card_id: str | None = None
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    device_id: str | None = None
    occurred_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise InvalidLoyaltyCardAuditFieldError("user_id requerido")
        if not self.operation_id:
            raise InvalidLoyaltyCardAuditFieldError("operation_id requerido")
        if not self.action:
            raise InvalidLoyaltyCardAuditFieldError("action requerido")
        if not self.branch_id:
            raise InvalidLoyaltyCardAuditFieldError("branch_id requerido")
