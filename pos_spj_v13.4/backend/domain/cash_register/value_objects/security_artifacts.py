"""Immutable evidence for hot authorization and security auditing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from backend.domain.cash_register.exceptions import CashAuthorizationRequiredError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _money(value: Decimal | str | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Cash Register monetary values must be Decimal")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Cash Register monetary values must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class CashAuthorizationGrant:
    requested_by: str
    authorized_by: str
    permission_code: str
    reason: str
    operation_id: str
    entity_id: str
    branch_id: str
    amount: Decimal | None = None
    device_id: str | None = None
    id: str = field(default_factory=new_uuid)
    authorized_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        required = (
            self.requested_by, self.authorized_by, self.permission_code,
            self.reason.strip(), self.operation_id, self.entity_id, self.branch_id,
        )
        if not all(required):
            raise CashAuthorizationRequiredError(
                "La autorización requiere actores, permiso, motivo, operación, entidad y sucursal")
        if self.requested_by == self.authorized_by:
            raise CashAuthorizationRequiredError(
                "El solicitante no puede autorizar su propia excepción de Caja")
        object.__setattr__(self, "amount", _money(self.amount))


@dataclass(frozen=True, slots=True)
class CashSecurityAuditEntry:
    action: str
    actor_user_id: str
    entity_id: str
    branch_id: str
    operation_id: str
    reason: str
    authorization_id: str | None = None
    amount: Decimal | None = None
    device_id: str | None = None
    id: str = field(default_factory=new_uuid)
    occurred_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not all((self.action, self.actor_user_id, self.entity_id,
                    self.branch_id, self.operation_id, self.reason.strip())):
            raise ValueError("La auditoría de Caja requiere acción, actor, entidad, sucursal, operación y motivo")
        object.__setattr__(self, "amount", _money(self.amount))

