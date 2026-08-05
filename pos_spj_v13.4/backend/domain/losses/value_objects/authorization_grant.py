"""Immutable audit record for an in-place Losses authorization."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def _decimal(value: Decimal | int | str, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name} debe usar Decimal, nunca float")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class LossAuthorizationGrant:
    permission_code: str
    requested_by: str
    authorized_by: str
    operation_id: str
    reason: str
    value_reference: Decimal
    approval_limit: Decimal
    branch_id: str
    warehouse_id: str | None = None
    device_id: str | None = None

    def __post_init__(self) -> None:
        required = {
            "permission_code": self.permission_code,
            "requested_by": self.requested_by,
            "authorized_by": self.authorized_by,
            "operation_id": self.operation_id,
            "reason": self.reason,
            "branch_id": self.branch_id,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ValueError("Campos de autorización requeridos: " + ", ".join(missing))
        object.__setattr__(self, "value_reference", _decimal(
            self.value_reference, field_name="value_reference"))
        object.__setattr__(self, "approval_limit", _decimal(
            self.approval_limit, field_name="approval_limit"))
