"""TRF-8 picking list, barcode, lot, and partial picking use cases."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.enums import TransferStatus
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferInvalidStatusError, TransferNotFoundError
from backend.domain.transfers.repository_ports import StockTransferRepository
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import (
    ConfirmTransferPickingCommand,
    StartTransferPickingCommand,
    TransferPickLineCommand,
)
from ..dto.picking_dto import TransferPickingListDTO, TransferPickingListLineDTO
from ..dto.transfer_request_dto import TransferRequestDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink, _dto, _record_operation


class TransferBarcodeValidator(Protocol):
    def validate_pick_scan(self, *, transfer: StockTransfer, transfer_line_id: str,
                           barcode: str | None, lot_id: str | None,
                           location_id: str | None) -> None: ...


def _picking_list(transfer: StockTransfer) -> TransferPickingListDTO:
    return TransferPickingListDTO(
        transfer_id=transfer.id,
        transfer_number=transfer.transfer_number,
        status=transfer.status.value,
        lines=tuple(
            TransferPickingListLineDTO(
                transfer_line_id=line.id,
                product_id=line.product_id,
                unit_id=line.unit_id,
                reserved_quantity=line.reserved_quantity,
                reserved_weight=line.reserved_weight,
                picked_quantity=line.picked_quantity,
                picked_weight=line.picked_weight,
                lot_required=line.lot_required,
                temperature_at_pick=line.temperature_at_pick,
            )
            for line in transfer.lines
        ),
    )


def _picked_values(command_lines: tuple[TransferPickLineCommand, ...],
                   transfer: StockTransfer) -> dict[str, tuple[object, object]]:
    if not command_lines:
        raise ValueError("Picking confirmation requires at least one scanned line")
    values = {line.transfer_line_id: (line.picked_quantity, line.picked_weight) for line in command_lines}
    if len(values) != len(command_lines):
        raise ValueError("Picking command contains duplicated transfer lines")
    transfer_line_ids = {line.id for line in transfer.lines}
    if not set(values).issubset(transfer_line_ids):
        raise ValueError("Picking command references a line outside this transfer")
    return values


class BuildTransferPickingListUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy) -> None:
        self._repository = repository
        self._authorization = authorization

    def execute(self, *, transfer_id: str, user_id: str) -> TransferPickingListDTO:
        transfer = self._repository.get(transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=user_id,
            permission_code=TransferPermissions.PICK,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        if transfer.status not in (TransferStatus.RESERVED, TransferStatus.PICKING, TransferStatus.PARTIALLY_PICKED):
            raise TransferInvalidStatusError("Picking list requires reserved inventory")
        return _picking_list(transfer)


class StartTransferPickingUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._event_sink = event_sink

    def execute(self, command: StartTransferPickingCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer picking operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=command.picker_user_id,
            permission_code=TransferPermissions.PICK,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        transfer.start_picking()
        self._repository.save(transfer)
        _record_operation(self._repository, transfer_id=transfer.id,
                          operation_id=command.operation_id, operation_type="TRANSFER_PICKING_START")
        self._collect(TransferEvents.PICKING_STARTED, command.operation_id, transfer.id, command.picker_user_id)
        return _dto(transfer)

    def _collect(self, event_name: str, operation_id: str, transfer_id: str, user_id: str) -> None:
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(event_name, operation_id=operation_id,
                                                  entity_id=transfer_id, user_id=user_id))


class ConfirmTransferPickingUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy,
                 barcode_validator: TransferBarcodeValidator | None = None,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._barcode_validator = barcode_validator
        self._event_sink = event_sink

    def execute(self, command: ConfirmTransferPickingCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer picking confirmation operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=command.picker_user_id,
            permission_code=TransferPermissions.PICK_CONFIRM,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        for line in command.lines:
            self._validate_scan(transfer, line)
        transfer.record_pick(_picked_values(command.lines, transfer))
        for observed in command.lines:
            transfer_line = next(line for line in transfer.lines if line.id == observed.transfer_line_id)
            if observed.temperature_at_pick is not None:
                if isinstance(observed.temperature_at_pick, (bool, float)):
                    raise TypeError("Picking temperature must use Decimal")
                transfer_line.temperature_at_pick = Decimal(str(observed.temperature_at_pick))
        self._repository.save(transfer)
        _record_operation(self._repository, transfer_id=transfer.id,
                          operation_id=command.operation_id, operation_type="TRANSFER_PICK_CONFIRM")
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                TransferEvents.PICKED,
                operation_id=command.operation_id,
                entity_id=transfer.id,
                user_id=command.picker_user_id,
                partial=transfer.status is TransferStatus.PARTIALLY_PICKED,
            ))
        return _dto(transfer)

    def _validate_scan(self, transfer: StockTransfer, line: TransferPickLineCommand) -> None:
        quantity = Decimal(str(line.picked_quantity))
        if quantity <= Decimal("0"):
            raise ValueError("Picking scan requires a positive quantity")
        transfer_line = next((existing for existing in transfer.lines if existing.id == line.transfer_line_id), None)
        if transfer_line is None:
            raise ValueError("Picking command references a line outside this transfer")
        if transfer_line.lot_required and not line.lot_id:
            raise ValueError("Lot-controlled transfer picking requires a lot scan")
        if transfer_line.temperature_required and line.temperature_at_pick is None:
            raise ValueError("Temperature-controlled picking requires temperature capture")
        if isinstance(line.temperature_at_pick, (bool, float)):
            raise TypeError("Picking temperature must use Decimal")
        if not line.location_id:
            raise ValueError("Transfer picking requires a source location scan")
        if self._barcode_validator is not None:
            self._barcode_validator.validate_pick_scan(
                transfer=transfer,
                transfer_line_id=line.transfer_line_id,
                barcode=line.barcode,
                lot_id=line.lot_id,
                location_id=line.location_id,
            )
