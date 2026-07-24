"""Non-executing transfer suggestion produced by configured analytics."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from ..value_objects.transfer_node import TransferNode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Transfer suggestion values must use Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TransferSuggestion:
    product_id: str
    unit_id: str
    origin_node: TransferNode
    destination_node: TransferNode
    suggested_quantity: Decimal
    origin_days_of_supply: Decimal
    destination_days_of_supply: Decimal
    target_days_of_supply: Decimal
    coefficient_of_variation: Decimal
    urgency_score: Decimal
    operation_id: str
    source_channel: str
    source_reference_id: str | None = None
    id: str = field(default_factory=new_uuid)
    status: str = "PROPOSED"
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        for name in (
            "suggested_quantity", "origin_days_of_supply", "destination_days_of_supply",
            "target_days_of_supply", "coefficient_of_variation", "urgency_score",
        ):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if self.suggested_quantity <= 0:
            raise ValueError("Transfer suggestion quantity must be positive")
        if self.origin_node.identity() == self.destination_node.identity():
            raise ValueError("Transfer suggestion nodes must differ")
        if self.status not in {"PROPOSED", "ACCEPTED", "DISMISSED", "EXPIRED"}:
            raise ValueError("Transfer suggestion status is invalid")
        if not self.operation_id or not self.source_channel:
            raise ValueError("Transfer suggestion requires operation and source channel")
