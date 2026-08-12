"""AuthorizationGrant — the audit record of a hot authorization (§52).

Every in-place exception (a consumption over tolerance, a manual weight outside
tolerance, an excepcional order release, …) produces one of these so the audit
trail answers who requested, who authorized, for how much and why — mirrors
`backend/domain/inventory/value_objects/authorization_grant.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError


def _opt_decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise MeatProcessingInvariantError(
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
            raise MeatProcessingInvariantError("permission_code requerido")
        if not self.authorized_by:
            raise MeatProcessingInvariantError("authorized_by requerido")
        if not self.operation_id:
            raise MeatProcessingInvariantError("operation_id requerido")
        if not (self.reason or "").strip():
            raise MeatProcessingInvariantError("La autorización requiere un motivo")
        for field_name in ("quantity", "weight", "value_reference"):
            object.__setattr__(self, field_name, _opt_decimal(getattr(self, field_name)))
