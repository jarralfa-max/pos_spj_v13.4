"""AuthorizationGrant — the audit record of a hot authorization (master
prompt §26 'Autorización en caliente').

Every in-place exception in Sales/POS (a protected discount, a price
override, a sale without stock, a cancellation, a return, a reprint, a
special-credit sale) produces one of these so the audit trail answers who
requested, who authorized, and why. Mirrors
backend/domain/inventory/value_objects/authorization_grant.py exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.sales.exceptions import InvalidSalesAuditFieldError


def _opt_decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidSalesAuditFieldError(
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
    sale_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidSalesAuditFieldError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidSalesAuditFieldError("authorized_by requerido")
        if not self.operation_id:
            raise InvalidSalesAuditFieldError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidSalesAuditFieldError("La autorización requiere un motivo")
        object.__setattr__(self, "amount", _opt_decimal(self.amount))
