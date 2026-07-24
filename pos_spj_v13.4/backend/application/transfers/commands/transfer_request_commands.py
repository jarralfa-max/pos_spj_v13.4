"""Command objects for TRF-5 request creation, edition, and submission."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.transfers.enums import (
    DifferenceResolutionType, DifferenceType, TransferReturnReason, TransferType,
)
from backend.domain.transfers.value_objects.transfer_node import TransferNode


@dataclass(frozen=True, slots=True)
class TransferRequestLineCommand:
    product_id: str
    unit_id: str
    requested_quantity: Decimal | str | int
    requested_weight: Decimal | str | int = Decimal("0")
    pieces: Decimal | str | int = Decimal("0")
    lot_required: bool = False
    quality_required: bool = False
    temperature_required: bool = False
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreateTransferRequestCommand:
    requested_by_user_id: str
    operation_id: str
    transfer_type: TransferType
    origin_node: TransferNode
    destination_node: TransferNode
    lines: tuple[TransferRequestLineCommand, ...]
    priority: str = "NORMAL"
    source_channel: str = "MANUAL"
    source_reference_id: str | None = None
    blind_receipt_required: bool = False
    transport_required: bool = False
    cold_chain_required: bool = False


@dataclass(frozen=True, slots=True)
class EditTransferRequestCommand:
    transfer_id: str
    edited_by_user_id: str
    operation_id: str
    lines: tuple[TransferRequestLineCommand, ...]
    priority: str
    source_reference_id: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitTransferRequestCommand:
    transfer_id: str
    submitted_by_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class TransferApprovalLineCommand:
    transfer_line_id: str
    approved_quantity: Decimal | str | int
    approved_weight: Decimal | str | int = Decimal("0")


@dataclass(frozen=True, slots=True)
class ApproveTransferRequestCommand:
    transfer_id: str
    approved_by_user_id: str
    operation_id: str
    lines: tuple[TransferApprovalLineCommand, ...] = ()
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RejectTransferRequestCommand:
    transfer_id: str
    rejected_by_user_id: str
    operation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReserveTransferLineCommand:
    transfer_line_id: str
    reserved_quantity: Decimal | str | int
    reserved_weight: Decimal | str | int = Decimal("0")


@dataclass(frozen=True, slots=True)
class ReserveTransferInventoryCommand:
    transfer_id: str
    reserved_by_user_id: str
    operation_id: str
    lines: tuple[ReserveTransferLineCommand, ...] = ()
    allocate_lots_fefo: bool = False


@dataclass(frozen=True, slots=True)
class StartTransferPickingCommand:
    transfer_id: str
    picker_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class TransferPickLineCommand:
    transfer_line_id: str
    picked_quantity: Decimal | str | int
    picked_weight: Decimal | str | int = Decimal("0")
    barcode: str | None = None
    lot_id: str | None = None
    location_id: str | None = None
    temperature_at_pick: Decimal | str | int | None = None


@dataclass(frozen=True, slots=True)
class ConfirmTransferPickingCommand:
    transfer_id: str
    picker_user_id: str
    operation_id: str
    lines: tuple[TransferPickLineCommand, ...]


@dataclass(frozen=True, slots=True)
class CreateTransferPackageCommand:
    transfer_id: str
    packed_by_user_id: str
    operation_id: str
    package_number: str
    package_type: str
    weight: Decimal | str | int
    tare: Decimal | str | int
    line_ids: tuple[str, ...]
    seal_number: str | None = None
    temperature: Decimal | str | int | None = None
    print_label: bool = True


@dataclass(frozen=True, slots=True)
class DispatchTransferShipmentLineCommand:
    transfer_line_id: str
    quantity: Decimal | str | int
    weight: Decimal | str | int = Decimal("0")


@dataclass(frozen=True, slots=True)
class DispatchTransferShipmentCommand:
    transfer_id: str
    dispatched_by_user_id: str
    verified_by_user_id: str
    custody_received_by_user_id: str
    operation_id: str
    shipment_number: str
    lines: tuple[DispatchTransferShipmentLineCommand, ...]
    carrier_id: str | None = None
    vehicle_id: str | None = None
    driver_id: str | None = None
    seal_number: str | None = None
    temperature_at_dispatch: Decimal | str | int | None = None
    evidence_reference: str | None = None


@dataclass(frozen=True, slots=True)
class ReceiveTransferLineCommand:
    transfer_line_id: str
    observed_quantity: Decimal | str | int
    observed_weight: Decimal | str | int = Decimal("0")
    accepted: bool = True
    lot_id: str | None = None
    observed_pieces: Decimal | str | int = Decimal("0")
    temperature: Decimal | str | int | None = None
    expires_on: str | None = None


@dataclass(frozen=True, slots=True)
class ConfirmTransferReceiptCommand:
    transfer_id: str
    shipment_id: str
    received_by_user_id: str
    operation_id: str
    lines: tuple[ReceiveTransferLineCommand, ...]
    qr_payload: str | None = None
    offline: bool = False
    device_id: str | None = None
    local_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class StartBlindReceiptCommand:
    transfer_id: str
    shipment_id: str
    receiver_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class CaptureBlindReceiptCommand:
    count_id: str
    receiver_user_id: str
    operation_id: str
    lines: tuple[ReceiveTransferLineCommand, ...]


@dataclass(frozen=True, slots=True)
class ConfirmBlindReceiptCommand:
    count_id: str
    receiver_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class DetectTransferDifferenceCommand:
    transfer_id: str
    transfer_line_id: str
    detected_by_user_id: str
    operation_id: str
    expected_quantity: Decimal | str | int
    actual_quantity: Decimal | str | int
    expected_weight: Decimal | str | int
    actual_weight: Decimal | str | int
    reported_type: DifferenceType | None = None
    severity: str = "WARNING"
    responsible_stage: str = "RECEIVING"
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewTransferDifferenceCommand:
    transfer_id: str
    difference_id: str
    reviewed_by_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class ResolveTransferDifferenceCommand:
    transfer_id: str
    difference_id: str
    resolved_by_user_id: str
    operation_id: str
    resolution_type: DifferenceResolutionType
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TransferReturnLineCommand:
    transfer_line_id: str
    quantity: Decimal | str | int
    weight: Decimal | str | int = Decimal("0")
    pieces: Decimal | str | int = Decimal("0")
    lot_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreateTransferReturnCommand:
    transfer_id: str
    requested_by_user_id: str
    operation_id: str
    reason: TransferReturnReason
    lines: tuple[TransferReturnLineCommand, ...]


@dataclass(frozen=True, slots=True)
class ApproveTransferReturnCommand:
    transfer_id: str
    return_id: str
    approved_by_user_id: str
    operation_id: str


@dataclass(frozen=True, slots=True)
class DispatchTransferReturnCommand:
    transfer_id: str
    return_id: str
    dispatched_by_user_id: str
    custody_received_by_user_id: str
    operation_id: str
    evidence_reference: str | None = None
    temperature: Decimal | str | int | None = None


@dataclass(frozen=True, slots=True)
class ReceiveTransferReturnLineCommand:
    return_line_id: str
    quantity: Decimal | str | int
    weight: Decimal | str | int = Decimal("0")


@dataclass(frozen=True, slots=True)
class ReceiveTransferReturnCommand:
    transfer_id: str
    return_id: str
    received_by_user_id: str
    custody_delivered_by_user_id: str
    operation_id: str
    lines: tuple[ReceiveTransferReturnLineCommand, ...]
    evidence_reference: str | None = None
    temperature: Decimal | str | int | None = None


@dataclass(frozen=True, slots=True)
class GenerateTransferSuggestionsCommand:
    requested_by_user_id: str
    operation_id: str
    source_channel: str
    source_reference_id: str | None = None
    product_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    configuration_branch_id: str | None = None
    transfer_type: TransferType = TransferType.REPLENISHMENT_TRANSFER
