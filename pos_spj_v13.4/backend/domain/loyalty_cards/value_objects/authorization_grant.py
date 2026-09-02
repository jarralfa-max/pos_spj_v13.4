"""AuthorizationGrant — the audit record of a hot authorization/approval in
the Loyalty Cards bounded context (master prompt §60: 'quien diseña
plantilla no la activa solo', 'quien genera lote no lo aprueba solo').

Mirrors ``backend/domain/sales/value_objects/authorization_grant.py``
exactly, kept as a separate class (not the loyalty package's) because
Loyalty Cards is its own bounded context with its own exception hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.loyalty_cards.exceptions import InvalidLoyaltyCardAuditFieldError


def _opt_decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidLoyaltyCardAuditFieldError(
            "amount debe ser Decimal, nunca float")
    return Decimal(str(value))


@dataclass(frozen=True)
class AuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    amount: Decimal | None = None
    card_id: str | None = None
    batch_id: str | None = None
    template_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidLoyaltyCardAuditFieldError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidLoyaltyCardAuditFieldError("authorized_by requerido")
        if not self.operation_id:
            raise InvalidLoyaltyCardAuditFieldError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidLoyaltyCardAuditFieldError("La autorización requiere un motivo")
        object.__setattr__(self, "amount", _opt_decimal(self.amount))
