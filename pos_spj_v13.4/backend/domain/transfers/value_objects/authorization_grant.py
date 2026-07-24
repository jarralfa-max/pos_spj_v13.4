"""Immutable evidence of a hot authorization for a sensitive transfer action."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from ..exceptions import TransferAuthorizationRequiredError


def _decimal(value: Decimal | str | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer authorization quantities and weights must be Decimal")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TransferAuthorizationGrant:
    requested_by: str
    authorized_by: str
    permission_code: str
    reason: str
    operation_id: str
    transfer_id: str
    shipment_id: str | None = None
    receipt_id: str | None = None
    quantity: Decimal | None = None
    weight: Decimal | None = None
    device_id: str | None = None
    id: str = field(default_factory=new_uuid)
    authorized_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if not all((self.requested_by, self.authorized_by, self.permission_code,
                    self.reason.strip(), self.operation_id, self.transfer_id)):
            raise TransferAuthorizationRequiredError("Hot authorization requires actor, permission, reason, operation, and transfer")
        if self.requested_by == self.authorized_by:
            raise TransferAuthorizationRequiredError("A requester cannot authorize their own exception")
        object.__setattr__(self, "quantity", _decimal(self.quantity))
        object.__setattr__(self, "weight", _decimal(self.weight))
