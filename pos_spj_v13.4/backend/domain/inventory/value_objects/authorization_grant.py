"""AuthorizationGrant — the audit record of a hot authorization (§48).

Every in-place exception (an over-limit adjustment, a manual weight outside
tolerance, a negative-inventory override, …) produces one of these so the audit
trail answers who requested, who authorized, for how much and why. Persistence
lands in INV-4; this is the immutable domain record the use cases build.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.exceptions import InvalidInventoryLimitError


def _opt_decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidInventoryLimitError(
            "quantity/weight/value_reference deben ser Decimal, nunca float")
    return Decimal(str(value))


@dataclass(frozen=True)
class AuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    quantity: Decimal | None = None
    weight: Decimal | None = None
    value_reference: Decimal | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        if not self.permission_code:
            raise InvalidInventoryLimitError("permission_code requerido")
        if not self.authorized_by:
            raise InvalidInventoryLimitError("authorized_by requerido")
        if not self.operation_id:
            raise InvalidInventoryLimitError("operation_id requerido")
        if not (self.reason or "").strip():
            raise InvalidInventoryLimitError("La autorización requiere un motivo")
        for field_name in ("quantity", "weight", "value_reference"):
            object.__setattr__(self, field_name, _opt_decimal(getattr(self, field_name)))
