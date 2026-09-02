"""LoyaltyAuditEntry — one auditable Fidelidad/Loyalty action (master prompt
§61: programas, reglas, membresías, puntos, reservas, canjes, expiraciones,
ajustes, reversos, niveles, recompensas, retos, referidos, campañas,
cupones, vales, sorteos, participaciones, ganadores, antifraude,
configuración).

Pure value object; persistence is ``backend/application/loyalty/audit.py``.
Mirrors ``backend/domain/sales/value_objects/sales_audit_entry.py`` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.loyalty.exceptions import InvalidLoyaltyAuditFieldError


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LoyaltyAuditEntry:
    user_id: str
    operation_id: str
    action: str
    branch_id: str
    authorized_by: str | None = None
    entity_id: str | None = None
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    device_id: str | None = None
    occurred_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not self.user_id:
            raise InvalidLoyaltyAuditFieldError("user_id requerido")
        if not self.operation_id:
            raise InvalidLoyaltyAuditFieldError("operation_id requerido")
        if not self.action:
            raise InvalidLoyaltyAuditFieldError("action requerido")
        if not self.branch_id:
            raise InvalidLoyaltyAuditFieldError("branch_id requerido")
