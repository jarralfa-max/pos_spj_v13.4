"""Canonical transfer aggregate: document workflow, not inventory ownership.

The aggregate records approved, reserved, picked, dispatched, and received
facts.  Inventory ledger postings remain behind application ports.  Every
quantity and weight is a :class:`Decimal`; a float is rejected at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from ..enums import (
    ColdChainStatus, DifferenceResolutionType, DifferenceStatus, DifferenceType,
    ReceiptQualityStatus, TransferStatus, TransferType,
)
from ..exceptions import (TransferAlreadyReceivedError, TransferApprovalRequiredError,
                          TransferCancellationNotAllowedError, TransferInvalidStatusError,
                          TransferDifferenceReviewRequiredError,
                          TransferOverReceiptError, TransferPickingNotCompleteError,
                          TransferSameOriginDestinationError)
from ..value_objects.transfer_node import TransferNode


ZERO = Decimal("0")
TRANSFER_PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "URGENT", "EMERGENCY"})


def _decimal(value: Decimal | str | int | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Transfer quantities and weights must be Decimal, never float")
    return Decimal(str(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class StockTransferLine:
    product_id: str
    unit_id: str
    requested_quantity: Decimal
    requested_weight: Decimal = ZERO
    id: str = field(default_factory=new_uuid)
    approved_quantity: Decimal = ZERO
    approved_weight: Decimal = ZERO
    reserved_quantity: Decimal = ZERO
    reserved_weight: Decimal = ZERO
    picked_quantity: Decimal = ZERO
    picked_weight: Decimal = ZERO
    dispatched_quantity: Decimal = ZERO
    dispatched_weight: Decimal = ZERO
    received_quantity: Decimal = ZERO
    received_weight: Decimal = ZERO
    accepted_quantity: Decimal = ZERO
    accepted_weight: Decimal = ZERO
    rejected_quantity: Decimal = ZERO
    rejected_weight: Decimal = ZERO
    pieces: Decimal = ZERO
    lot_required: bool = False
    quality_required: bool = False
    temperature_required: bool = False
    temperature_at_pick: Decimal | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "requested_quantity", "requested_weight", "approved_quantity", "approved_weight",
            "reserved_quantity", "reserved_weight", "picked_quantity", "picked_weight",
            "dispatched_quantity", "dispatched_weight", "received_quantity", "received_weight",
            "accepted_quantity", "accepted_weight", "rejected_quantity", "rejected_weight", "pieces",
        ):
            setattr(self, field_name, _decimal(getattr(self, field_name)))
        if not self.product_id or not self.unit_id or self.requested_quantity <= ZERO:
            raise ValueError("A transfer line requires product, unit UUID, and positive quantity")
        if self.temperature_at_pick is not None:
            self.temperature_at_pick = _decimal(self.temperature_at_pick)

    @property
    def dispatchable_quantity(self) -> Decimal:
        return self.picked_quantity - self.dispatched_quantity

    @property
    def receivable_quantity(self) -> Decimal:
        return self.dispatched_quantity - self.received_quantity

    def approve(self, quantity: Decimal | str | int | None = None, weight: Decimal | str | int | None = None) -> None:
        quantity = _decimal(self.requested_quantity if quantity is None else quantity)
        weight = _decimal(self.requested_weight if weight is None else weight)
        if quantity < ZERO or quantity > self.requested_quantity or weight < ZERO or weight > self.requested_weight:
            raise TransferApprovalRequiredError("Approved line values must not exceed requested values")
        self.approved_quantity, self.approved_weight = quantity, weight

    def reserve(self, quantity: Decimal | str | int, weight: Decimal | str | int = ZERO) -> None:
        quantity, weight = _decimal(quantity), _decimal(weight)
        if quantity < ZERO or quantity > self.approved_quantity or weight < ZERO or weight > self.approved_weight:
            raise TransferApprovalRequiredError("Reservation exceeds approved line values")
        self.reserved_quantity, self.reserved_weight = quantity, weight

    def pick(self, quantity: Decimal | str | int, weight: Decimal | str | int = ZERO) -> None:
        quantity, weight = _decimal(quantity), _decimal(weight)
        if quantity < ZERO or quantity > self.reserved_quantity or weight < ZERO or weight > self.reserved_weight:
            raise TransferPickingNotCompleteError("Picking exceeds reserved line values")
        self.picked_quantity, self.picked_weight = quantity, weight

    def dispatch(self, quantity: Decimal | str | int, weight: Decimal | str | int = ZERO) -> None:
        quantity, weight = _decimal(quantity), _decimal(weight)
        if quantity <= ZERO or quantity > self.dispatchable_quantity or weight < ZERO or weight > self.picked_weight - self.dispatched_weight:
            raise TransferPickingNotCompleteError("Dispatch exceeds picked line values")
        self.dispatched_quantity += quantity
        self.dispatched_weight += weight

    def receive(self, quantity: Decimal | str | int, weight: Decimal | str | int, *, accepted: bool) -> None:
        quantity, weight = _decimal(quantity), _decimal(weight)
        if quantity < ZERO or weight < ZERO or quantity > self.receivable_quantity or weight > self.dispatched_weight - self.received_weight:
            raise TransferOverReceiptError("Receipt exceeds dispatched line values")
        self.received_quantity += quantity
        self.received_weight += weight
        if accepted:
            self.accepted_quantity += quantity
            self.accepted_weight += weight
        else:
            self.rejected_quantity += quantity
            self.rejected_weight += weight


@dataclass(frozen=True, slots=True)
class TransferReceiptLine:
    transfer_line_id: str
    observed_quantity: Decimal
    observed_weight: Decimal = ZERO
    accepted: bool = True
    lot_id: str | None = None
    observed_pieces: Decimal = ZERO
    temperature: Decimal | None = None
    expires_on: str | None = None
    cold_chain_status: ColdChainStatus = ColdChainStatus.COMPLIANT
    quality_status: ReceiptQualityStatus = ReceiptQualityStatus.AVAILABLE

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_quantity", _decimal(self.observed_quantity))
        object.__setattr__(self, "observed_weight", _decimal(self.observed_weight))
        object.__setattr__(self, "observed_pieces", _decimal(self.observed_pieces))
        if self.temperature is not None:
            object.__setattr__(self, "temperature", _decimal(self.temperature))
        if (self.observed_quantity < ZERO or self.observed_weight < ZERO
                or self.observed_pieces < ZERO):
            raise ValueError("Negative receipt is invalid")
        if self.observed_pieces != self.observed_pieces.to_integral_value():
            raise ValueError("Received pieces must be a whole Decimal value")


@dataclass(frozen=True, slots=True)
class TransferReceipt:
    shipment_id: str
    received_by_user_id: str
    lines: tuple[TransferReceiptLine, ...]
    operation_id: str
    device_id: str | None = None
    local_sequence: int | None = None
    sync_status: str = "CONFIRMED"
    qr_reference: str | None = None
    id: str = field(default_factory=new_uuid)
    received_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.shipment_id or not self.received_by_user_id or not self.operation_id or not self.lines:
            raise ValueError("Receipt requires shipment, receiver, operation, and at least one line")
        if len({line.transfer_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("A receipt may contain each transfer line only once")
        if self.sync_status not in {"PENDING", "CONFIRMED"}:
            raise ValueError("Receipt sync status is invalid")
        if self.sync_status == "PENDING" and (
            not self.device_id or self.local_sequence is None or self.local_sequence < 1
        ):
            raise ValueError("Offline receipt requires device and positive local sequence")


@dataclass(slots=True)
class TransferDifference:
    transfer_line_id: str
    difference_type: DifferenceType
    expected_quantity: Decimal
    actual_quantity: Decimal
    expected_weight: Decimal
    actual_weight: Decimal
    id: str = field(default_factory=new_uuid)
    severity: str = "WARNING"
    responsible_stage: str = "RECEIVING"
    status: DifferenceStatus = DifferenceStatus.DETECTED
    evidence: tuple[str, ...] = ()
    detected_by_user_id: str | None = None
    detected_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.expected_quantity = _decimal(self.expected_quantity)
        self.actual_quantity = _decimal(self.actual_quantity)
        self.expected_weight = _decimal(self.expected_weight)
        self.actual_weight = _decimal(self.actual_weight)
        if self.severity not in {"INFO", "WARNING", "DANGER", "CRITICAL"}:
            raise ValueError("Difference severity is invalid")
        if not self.responsible_stage:
            raise ValueError("Difference responsible stage is required")
        if any(not reference.strip() for reference in self.evidence):
            raise ValueError("Difference evidence references cannot be empty")

    @property
    def quantity_delta(self) -> Decimal:
        return self.actual_quantity - self.expected_quantity

    @property
    def weight_delta(self) -> Decimal:
        return self.actual_weight - self.expected_weight

    def submit_for_review(self) -> None:
        if self.status is not DifferenceStatus.DETECTED:
            raise TransferInvalidStatusError("Only detected differences can enter review")
        self.status = DifferenceStatus.PENDING_REVIEW

    def resolve(self) -> None:
        if self.status not in {DifferenceStatus.PENDING_REVIEW, DifferenceStatus.UNDER_INVESTIGATION}:
            raise TransferDifferenceReviewRequiredError("Difference review is required before resolution")
        self.status = DifferenceStatus.RESOLVED


@dataclass(frozen=True, slots=True)
class TransferDifferenceResolution:
    difference_id: str
    resolution_type: DifferenceResolutionType
    resolved_by_user_id: str
    operation_id: str
    reason: str
    evidence: tuple[str, ...] = ()
    id: str = field(default_factory=new_uuid)
    resolved_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not all((self.difference_id, self.resolved_by_user_id, self.operation_id,
                    self.reason.strip())):
            raise ValueError("Difference resolution requires identity, resolver, operation, and reason")
        if any(not reference.strip() for reference in self.evidence):
            raise ValueError("Resolution evidence references cannot be empty")


@dataclass(slots=True)
class StockTransfer:
    transfer_number: str
    transfer_type: TransferType
    origin_node: TransferNode
    destination_node: TransferNode
    requested_by_user_id: str
    operation_id: str
    lines: list[StockTransferLine]
    id: str = field(default_factory=new_uuid)
    status: TransferStatus = TransferStatus.DRAFT
    approved_by_user_id: str | None = None
    priority: str = "NORMAL"
    source_channel: str = "MANUAL"
    source_reference_id: str | None = None
    blind_receipt_required: bool = False
    transport_required: bool = False
    cold_chain_required: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    _receipt_operations: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not self.transfer_number or not self.requested_by_user_id or not self.operation_id:
            raise ValueError("Transfer number, requester, and operation are required")
        if self.origin_node.identity() == self.destination_node.identity():
            raise TransferSameOriginDestinationError("Origin and destination must differ")
        if not self.lines or len({line.id for line in self.lines}) != len(self.lines):
            raise ValueError("A transfer needs unique lines")
        self.validate_priority()

    def validate_priority(self) -> None:
        if self.priority not in TRANSFER_PRIORITIES:
            raise ValueError(f"Unknown transfer priority: {self.priority}")

    def _transition(self, allowed: tuple[TransferStatus, ...], target: TransferStatus) -> None:
        if self.status not in allowed:
            raise TransferInvalidStatusError(f"{self.status.value} cannot transition to {target.value}")
        self.status = target
        self.updated_at = _now()

    def edit_request(self, *, lines: list[StockTransferLine], priority: str,
                     source_reference_id: str | None = None) -> None:
        if self.status is not TransferStatus.DRAFT:
            raise TransferInvalidStatusError("Only draft transfer requests can be edited")
        if not lines or len({line.id for line in lines}) != len(lines):
            raise ValueError("A transfer request edit requires unique lines")
        self.lines = lines
        self.priority = priority
        self.source_reference_id = source_reference_id
        self.validate_priority()
        self.updated_at = _now()

    def submit(self) -> None:
        self._transition((TransferStatus.DRAFT,), TransferStatus.PENDING_APPROVAL)

    def approve(self, user_id: str, approved: dict[str, tuple[Decimal | str | int, Decimal | str | int]] | None = None) -> None:
        self._transition((TransferStatus.PENDING_APPROVAL,), TransferStatus.APPROVED)
        for line in self.lines:
            quantity, weight = (approved or {}).get(line.id, (line.requested_quantity, line.requested_weight))
            line.approve(quantity, weight)
        if not any(line.approved_quantity > ZERO for line in self.lines):
            raise TransferApprovalRequiredError("An approval must approve at least one line")
        self.approved_by_user_id = user_id

    def reject(self) -> None:
        self._transition((TransferStatus.PENDING_APPROVAL,), TransferStatus.REJECTED)

    def begin_reservation(self) -> None:
        self._transition((TransferStatus.APPROVED,), TransferStatus.RESERVATION_PENDING)

    def reserve(self, reserved: dict[str, tuple[Decimal | str | int, Decimal | str | int]] | None = None) -> None:
        self._transition((TransferStatus.APPROVED, TransferStatus.RESERVATION_PENDING), TransferStatus.RESERVED)
        for line in self.lines:
            quantity, weight = (reserved or {}).get(line.id, (line.approved_quantity, line.approved_weight))
            line.reserve(quantity, weight)

    def start_picking(self) -> None:
        self._transition((TransferStatus.RESERVED, TransferStatus.PARTIALLY_PICKED), TransferStatus.PICKING)

    def record_pick(self, picked: dict[str, tuple[Decimal | str | int, Decimal | str | int]]) -> None:
        if self.status not in (TransferStatus.PICKING, TransferStatus.PARTIALLY_PICKED):
            raise TransferInvalidStatusError("Picking requires a reserved transfer")
        for line in self.lines:
            if line.id in picked:
                line.pick(*picked[line.id])
        self.status = TransferStatus.PICKED if all(line.picked_quantity == line.reserved_quantity for line in self.lines) else TransferStatus.PARTIALLY_PICKED
        self.updated_at = _now()

    def ready_to_dispatch(self) -> None:
        self._transition((TransferStatus.PICKING, TransferStatus.PARTIALLY_PICKED, TransferStatus.PICKED), TransferStatus.READY_TO_DISPATCH)

    def record_dispatch(self, quantities: dict[str, Decimal | str | int], weights: dict[str, Decimal | str | int] | None = None) -> None:
        if self.status not in (TransferStatus.READY_TO_DISPATCH, TransferStatus.PARTIALLY_DISPATCHED):
            raise TransferInvalidStatusError("Dispatch requires a ready transfer")
        for line in self.lines:
            quantity = quantities.get(line.id, ZERO)
            if _decimal(quantity) > ZERO:
                line.dispatch(quantity, (weights or {}).get(line.id, ZERO))
        self.status = TransferStatus.IN_TRANSIT if all(line.dispatched_quantity == line.picked_quantity for line in self.lines) else TransferStatus.PARTIALLY_DISPATCHED
        self.updated_at = _now()

    def receive(self, receipt: TransferReceipt, *, over_receipt_allowed: bool = False) -> list[TransferDifference]:
        if receipt.operation_id in self._receipt_operations:
            raise TransferAlreadyReceivedError("Receipt operation was already applied")
        if self.status not in (TransferStatus.IN_TRANSIT, TransferStatus.PARTIALLY_RECEIVED):
            raise TransferInvalidStatusError("Receipt requires inventory in transit")
        lines = {line.id: line for line in self.lines}
        before = {line.id: (line.received_quantity, line.received_weight) for line in self.lines}
        differences: list[TransferDifference] = []
        for observed in receipt.lines:
            if observed.transfer_line_id not in lines:
                raise TransferOverReceiptError("Receipt references a line outside this transfer")
            line = lines[observed.transfer_line_id]
            if not over_receipt_allowed and (observed.observed_quantity > line.receivable_quantity or observed.observed_weight > line.dispatched_weight - line.received_weight):
                raise TransferOverReceiptError("Receipt exceeds dispatched line values")
            line.receive(observed.observed_quantity, observed.observed_weight, accepted=observed.accepted)
            if not observed.accepted:
                expected_quantity, expected_weight = before[line.id]
                differences.append(TransferDifference(line.id, DifferenceType.SHORT_QUANTITY, line.dispatched_quantity - expected_quantity, observed.observed_quantity, line.dispatched_weight - expected_weight, observed.observed_weight))
        self._receipt_operations.add(receipt.operation_id)
        complete = all(line.received_quantity == line.dispatched_quantity and line.received_weight == line.dispatched_weight for line in self.lines)
        self.status = TransferStatus.WITH_DIFFERENCES if differences else (TransferStatus.RECEIVED if complete else TransferStatus.PARTIALLY_RECEIVED)
        self.updated_at = _now()
        return differences

    def mark_pending_resolution(self) -> None:
        self._transition((TransferStatus.WITH_DIFFERENCES,), TransferStatus.PENDING_RESOLUTION)

    def register_difference(self) -> None:
        if self.status is TransferStatus.RECEIVED:
            self.status = TransferStatus.WITH_DIFFERENCES
            self.updated_at = _now()
        elif self.status not in {TransferStatus.PARTIALLY_RECEIVED, TransferStatus.WITH_DIFFERENCES}:
            raise TransferInvalidStatusError("Differences require a received transfer")

    def begin_return(self) -> None:
        self._transition(
            (TransferStatus.RECEIVED, TransferStatus.WITH_DIFFERENCES,
             TransferStatus.PENDING_RESOLUTION),
            TransferStatus.RETURN_IN_PROGRESS,
        )

    def complete_return(self) -> None:
        self._transition((TransferStatus.RETURN_IN_PROGRESS,), TransferStatus.CLOSED)

    def close(self) -> None:
        self._transition((TransferStatus.RECEIVED, TransferStatus.PENDING_RESOLUTION), TransferStatus.CLOSED)

    def cancel(self) -> None:
        if self.status in (TransferStatus.IN_TRANSIT, TransferStatus.PARTIALLY_RECEIVED, TransferStatus.RECEIVED, TransferStatus.WITH_DIFFERENCES, TransferStatus.PENDING_RESOLUTION):
            raise TransferCancellationNotAllowedError("Dispatched stock must use return or reversal workflow")
        self._transition((TransferStatus.DRAFT, TransferStatus.PENDING_APPROVAL, TransferStatus.APPROVED, TransferStatus.RESERVATION_PENDING, TransferStatus.RESERVED, TransferStatus.PICKING, TransferStatus.PARTIALLY_PICKED, TransferStatus.PICKED, TransferStatus.READY_TO_DISPATCH), TransferStatus.CANCELLED)
