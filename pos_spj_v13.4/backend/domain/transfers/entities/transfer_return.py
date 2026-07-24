"""Return-to-origin aggregate with independent custody, transit and receipt."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from ..enums import TransferReturnReason, TransferReturnStatus
from ..exceptions import SegregationOfDutiesError, TransferInvalidStatusError, TransferOverReceiptError
from ..value_objects.transfer_node import TransferNode


ZERO = Decimal("0")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Transfer return values must use Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(slots=True)
class TransferReturnLine:
    transfer_line_id: str
    quantity: Decimal
    weight: Decimal = ZERO
    pieces: Decimal = ZERO
    lot_id: str | None = None
    id: str = field(default_factory=new_uuid)
    dispatched_quantity: Decimal = ZERO
    dispatched_weight: Decimal = ZERO
    received_quantity: Decimal = ZERO
    received_weight: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in ("quantity", "weight", "pieces", "dispatched_quantity",
                     "dispatched_weight", "received_quantity", "received_weight"):
            setattr(self, name, _decimal(getattr(self, name)))
        if not self.transfer_line_id or self.quantity <= ZERO or self.weight < ZERO:
            raise ValueError("Return line requires transfer line and positive quantity")
        if self.pieces < ZERO or self.pieces != self.pieces.to_integral_value():
            raise ValueError("Return pieces must be a nonnegative whole Decimal")

    def dispatch(self) -> None:
        self.dispatched_quantity, self.dispatched_weight = self.quantity, self.weight

    def receive(self, quantity: Decimal | str | int, weight: Decimal | str | int) -> None:
        quantity, weight = _decimal(quantity), _decimal(weight)
        if (quantity < ZERO or weight < ZERO or quantity > self.dispatched_quantity
                or weight > self.dispatched_weight):
            raise TransferOverReceiptError("Return receipt exceeds dispatched values")
        self.received_quantity, self.received_weight = quantity, weight


@dataclass(frozen=True, slots=True)
class TransferReturnCustodyEvent:
    return_id: str
    event_type: str
    delivered_by_user_id: str
    received_by_user_id: str
    location_id: str | None
    evidence_reference: str | None = None
    temperature: Decimal | None = None
    id: str = field(default_factory=new_uuid)
    occurred_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.delivered_by_user_id == self.received_by_user_id:
            raise ValueError("Return custody handover requires distinct parties")
        if self.temperature is not None:
            object.__setattr__(self, "temperature", _decimal(self.temperature))


@dataclass(slots=True)
class TransferReturn:
    transfer_id: str
    return_number: str
    reason: TransferReturnReason
    source_node: TransferNode
    destination_node: TransferNode
    requested_by_user_id: str
    request_operation_id: str
    lines: list[TransferReturnLine]
    id: str = field(default_factory=new_uuid)
    status: TransferReturnStatus = TransferReturnStatus.REQUESTED
    approved_by_user_id: str | None = None
    dispatched_by_user_id: str | None = None
    received_by_user_id: str | None = None
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None

    def __post_init__(self) -> None:
        if not self.lines or len({line.transfer_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("Return requires unique transfer lines")
        if self.source_node.identity() == self.destination_node.identity():
            raise ValueError("Return source and destination must differ")

    def approve(self, user_id: str) -> None:
        if self.status is not TransferReturnStatus.REQUESTED:
            raise TransferInvalidStatusError("Only requested returns can be approved")
        if user_id == self.requested_by_user_id:
            raise SegregationOfDutiesError("Return approval requires an independent user")
        self.approved_by_user_id, self.status = user_id, TransferReturnStatus.APPROVED

    def dispatch(self, user_id: str) -> None:
        if self.status is not TransferReturnStatus.APPROVED:
            raise TransferInvalidStatusError("Return dispatch requires approval")
        for line in self.lines:
            line.dispatch()
        self.dispatched_by_user_id, self.status = user_id, TransferReturnStatus.DISPATCHED

    def mark_in_transit(self) -> None:
        if self.status is not TransferReturnStatus.DISPATCHED:
            raise TransferInvalidStatusError("Return transit requires confirmed dispatch")
        self.status = TransferReturnStatus.IN_TRANSIT

    def receive(self, user_id: str,
                values: dict[str, tuple[Decimal | str | int, Decimal | str | int]]) -> None:
        if self.status is not TransferReturnStatus.IN_TRANSIT:
            raise TransferInvalidStatusError("Return receipt requires inventory in transit")
        if user_id == self.dispatched_by_user_id:
            raise SegregationOfDutiesError("Return dispatcher cannot confirm origin receipt")
        if set(values) != {line.id for line in self.lines}:
            raise ValueError("Return receipt must include exactly every dispatched line")
        for line in self.lines:
            quantity, weight = (_decimal(value) for value in values[line.id])
            if quantity != line.dispatched_quantity or weight != line.dispatched_weight:
                raise TransferOverReceiptError("Return receipt must match dispatched values")
        for line in self.lines:
            line.receive(*values[line.id])
        self.received_by_user_id = user_id
        self.status = TransferReturnStatus.RECEIVED

    def complete(self) -> None:
        if self.status is not TransferReturnStatus.RECEIVED:
            raise TransferInvalidStatusError("Return completion requires origin receipt")
        self.status = TransferReturnStatus.COMPLETED
        self.completed_at = _now()
