"""AuthorizationGrant — the audit record of a hot authorization/approval in
the Fidelidad/Loyalty bounded context (master prompt §60).

Covers every in-place second-approval action across the whole loyalty area:
a points adjustment approval, a campaign activation, a coupon override, a
raffle activation/winner draw authorization, etc. Mirrors
``backend/domain/sales/value_objects/authorization_grant.py`` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.loyalty.exceptions import InvalidLoyaltyAuditFieldError


def _opt_decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidLoyaltyAuditFieldError(
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
    entity_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidLoyaltyAuditFieldError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidLoyaltyAuditFieldError("authorized_by requerido")
        if not self.operation_id:
            raise InvalidLoyaltyAuditFieldError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidLoyaltyAuditFieldError("La autorización requiere un motivo")
        object.__setattr__(self, "amount", _opt_decimal(self.amount))
