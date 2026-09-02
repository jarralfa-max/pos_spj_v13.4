"""AuthorizationGrant — the audit record of a hot authorization/approval in
the Pedidos/Delivery bounded context (master prompt §65).

Covers every in-place second-approval action across the whole area: a
catch-weight override outside tolerance, an exceptional substitution,
cancellation after preparation started, a delivery confirmed without
required evidence, an incomplete cash-on-delivery collection, a driver
settlement cash difference, a delivered-order reversal, a refund. Mirrors
``backend/domain/loyalty/value_objects/authorization_grant.py`` exactly,
plus optional ``quantity``/``weight``/``order_id``/``delivery_job_id`` fields
since master prompt §65 explicitly lists those as required audit columns for
this bounded context (unlike Loyalty, which only needed ``amount``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.orders_delivery.exceptions import InvalidOrdersDeliveryAuditFieldError


def _opt_decimal(value: Decimal | int | str | None, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidOrdersDeliveryAuditFieldError(
            f"{field_name} debe ser Decimal, nunca float")
    return Decimal(str(value))


@dataclass(frozen=True)
class AuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    amount: Decimal | None = None
    quantity: Decimal | None = None
    weight: Decimal | None = None
    order_id: str | None = None
    delivery_job_id: str | None = None
    entity_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidOrdersDeliveryAuditFieldError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidOrdersDeliveryAuditFieldError("authorized_by requerido")
        if not self.operation_id:
            raise InvalidOrdersDeliveryAuditFieldError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidOrdersDeliveryAuditFieldError("La autorización requiere un motivo")
        object.__setattr__(self, "amount", _opt_decimal(self.amount, "amount"))
        object.__setattr__(self, "quantity", _opt_decimal(self.quantity, "quantity"))
        object.__setattr__(self, "weight", _opt_decimal(self.weight, "weight"))
