"""TRF-12 protected blind-count workflow and post-confirmation revelation."""
from __future__ import annotations

from backend.domain.transfers.entities.blind_receipt_count import (
    BlindReceiptCount,
    BlindReceiptObservedLine,
)
from backend.domain.transfers.exceptions import (
    DuplicateOperationError,
    PermissionDeniedError,
    TransferNotFoundError,
)
from backend.domain.transfers.repository_ports import (
    BlindReceiptCountRepository,
    StockTransferRepository,
    TransferReceiptRepository,
    TransferShipmentRepository,
)
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import (
    CaptureBlindReceiptCommand,
    ConfirmBlindReceiptCommand,
    ConfirmTransferReceiptCommand,
    ReceiveTransferLineCommand,
    StartBlindReceiptCommand,
)
from ..dto.blind_receipt_dto import (
    BlindReceiptComparisonLineDTO,
    BlindReceiptCountDTO,
    BlindReceiptObservedLineDTO,
    ConfirmedBlindReceiptDTO,
)
from ..permissions import TransferPermissions
from .transfer_receipt_use_cases import ConfirmTransferReceiptUseCase, _decimal


class _BlindReceiptBase:
    def __init__(self, transfer_repository: StockTransferRepository,
                 count_repository: BlindReceiptCountRepository,
                 authorization: TransferAuthorizationPolicy) -> None:
        self._transfers = transfer_repository
        self._counts = count_repository
        self._authorization = authorization

    def _load(self, count_id: str, receiver_user_id: str) -> tuple[BlindReceiptCount, object]:
        count = self._counts.get(count_id)
        if count is None:
            raise TransferNotFoundError("Blind receipt count not found")
        if count.receiver_user_id != receiver_user_id:
            raise PermissionDeniedError("Only the assigned receiver may operate this blind count")
        transfer = self._transfers.get(count.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=receiver_user_id,
            permission_code=TransferPermissions.BLIND_RECEIVE,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        return count, transfer


def _count_dto(count: BlindReceiptCount) -> BlindReceiptCountDTO:
    return BlindReceiptCountDTO(
        count_id=count.id,
        transfer_id=count.transfer_id,
        shipment_id=count.shipment_id,
        status=count.status,
        lines=tuple(BlindReceiptObservedLineDTO(
            line.transfer_line_id, line.observed_quantity, line.observed_weight,
            line.observed_pieces, line.temperature, line.expires_on,
        ) for line in count.lines),
    )


class StartBlindReceiptUseCase(_BlindReceiptBase):
    def __init__(self, transfer_repository: StockTransferRepository,
                 shipment_repository: TransferShipmentRepository,
                 count_repository: BlindReceiptCountRepository,
                 authorization: TransferAuthorizationPolicy) -> None:
        super().__init__(transfer_repository, count_repository, authorization)
        self._shipments = shipment_repository

    def execute(self, command: StartBlindReceiptCommand) -> BlindReceiptCountDTO:
        if self._counts.operation_exists(command.operation_id):
            raise DuplicateOperationError("Blind receipt start operation already exists")
        transfer = self._transfers.get(command.transfer_id)
        shipment = self._shipments.get(command.shipment_id)
        if transfer is None or shipment is None or shipment.transfer_id != command.transfer_id:
            raise TransferNotFoundError("Transfer shipment not found")
        if not transfer.blind_receipt_required:
            raise PermissionDeniedError("Blind receipt is not enabled for this transfer")
        self._authorization.require(
            user_id=command.receiver_user_id,
            permission_code=TransferPermissions.BLIND_RECEIVE,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        count = BlindReceiptCount(
            transfer_id=transfer.id,
            shipment_id=shipment.id,
            receiver_user_id=command.receiver_user_id,
            start_operation_id=command.operation_id,
        )
        self._counts.save(count)
        self._counts.record_operation(
            count_id=count.id, transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="BLIND_RECEIPT_STARTED", actor_id=command.receiver_user_id,
        )
        return _count_dto(count)


class CaptureBlindReceiptUseCase(_BlindReceiptBase):
    def execute(self, command: CaptureBlindReceiptCommand) -> BlindReceiptCountDTO:
        if self._counts.operation_exists(command.operation_id):
            raise DuplicateOperationError("Blind receipt capture operation already exists")
        count, transfer = self._load(command.count_id, command.receiver_user_id)
        count.capture(tuple(BlindReceiptObservedLine(
            transfer_line_id=line.transfer_line_id,
            observed_quantity=line.observed_quantity, observed_weight=line.observed_weight,
            accepted=line.accepted, lot_id=line.lot_id,
            observed_pieces=line.observed_pieces, temperature=line.temperature,
            expires_on=line.expires_on,
        ) for line in command.lines))
        self._counts.save(count)
        self._counts.record_operation(
            count_id=count.id, transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="BLIND_RECEIPT_CAPTURED", actor_id=command.receiver_user_id,
        )
        return _count_dto(count)


class ConfirmBlindReceiptUseCase(_BlindReceiptBase):
    def __init__(self, transfer_repository: StockTransferRepository,
                 shipment_repository: TransferShipmentRepository,
                 receipt_repository: TransferReceiptRepository,
                 count_repository: BlindReceiptCountRepository,
                 authorization: TransferAuthorizationPolicy,
                 receipt_use_case: ConfirmTransferReceiptUseCase) -> None:
        super().__init__(transfer_repository, count_repository, authorization)
        self._shipments = shipment_repository
        self._receipts = receipt_repository
        self._receipt_use_case = receipt_use_case

    def execute(self, command: ConfirmBlindReceiptCommand) -> ConfirmedBlindReceiptDTO:
        if self._counts.operation_exists(command.operation_id):
            raise DuplicateOperationError("Blind receipt confirmation operation already exists")
        count, _transfer = self._load(command.count_id, command.receiver_user_id)
        shipment = self._shipments.get(count.shipment_id)
        if shipment is None:
            raise TransferNotFoundError("Transfer shipment not found")
        already_received = self._receipts.received_totals(shipment.id)
        expected = {
            line.transfer_line_id: (
                line.quantity - _decimal(already_received.get(line.transfer_line_id, (0, 0))[0]),
                line.weight - _decimal(already_received.get(line.transfer_line_id, (0, 0))[1]),
            ) for line in shipment.lines
        }
        receipt = self._receipt_use_case.execute(ConfirmTransferReceiptCommand(
            transfer_id=count.transfer_id,
            shipment_id=count.shipment_id,
            received_by_user_id=command.receiver_user_id,
            operation_id=command.operation_id,
            lines=tuple(ReceiveTransferLineCommand(
                transfer_line_id=line.transfer_line_id,
                observed_quantity=line.observed_quantity, observed_weight=line.observed_weight,
                accepted=line.accepted, lot_id=line.lot_id,
                observed_pieces=line.observed_pieces, temperature=line.temperature,
                expires_on=line.expires_on,
            ) for line in count.lines),
        ))
        count.confirm(receipt.receipt_id)
        self._counts.save(count)
        observed = {line.transfer_line_id: line for line in count.lines}
        comparisons = tuple(
            BlindReceiptComparisonLineDTO(
                transfer_line_id=line_id,
                expected_quantity=values[0],
                observed_quantity=observed[line_id].observed_quantity,
                quantity_difference=observed[line_id].observed_quantity - values[0],
                expected_weight=values[1],
                observed_weight=observed[line_id].observed_weight,
                weight_difference=observed[line_id].observed_weight - values[1],
            )
            for line_id, values in expected.items() if line_id in observed
        )
        return ConfirmedBlindReceiptDTO(
            count_id=count.id, receipt_id=receipt.receipt_id,
            transfer_status=receipt.transfer_status,
            status=count.status, comparisons=comparisons,
        )
