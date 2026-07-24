"""TRF-15 return-to-origin request, dispatch, transit and receipt workflow."""
from __future__ import annotations

from typing import Protocol

from backend.domain.transfers.entities.transfer_return import (
    TransferReturn,
    TransferReturnCustodyEvent,
    TransferReturnLine,
)
from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import (
    DuplicateOperationError,
    TransferNotFoundError,
    TransferOverReceiptError,
)
from backend.domain.transfers.repository_ports import (
    InventoryTransferGateway,
    StockTransferRepository,
    TransferReturnRepository,
)
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import (
    ApproveTransferReturnCommand,
    CreateTransferReturnCommand,
    DispatchTransferReturnCommand,
    ReceiveTransferReturnCommand,
)
from ..dto.return_dto import TransferReturnDTO, TransferReturnLineDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink


class TransferReturnNumberGenerator(Protocol):
    def next_return_number(self) -> str: ...


def _dto(transfer_return: TransferReturn,
         custody: TransferReturnCustodyEvent | None = None) -> TransferReturnDTO:
    return TransferReturnDTO(
        return_id=transfer_return.id, transfer_id=transfer_return.transfer_id,
        return_number=transfer_return.return_number, reason=transfer_return.reason.value,
        status=transfer_return.status.value,
        source_node=transfer_return.source_node.identity(),
        destination_node=transfer_return.destination_node.identity(),
        custody_event_id=custody.id if custody is not None else None,
        lines=tuple(TransferReturnLineDTO(
            line.id, line.transfer_line_id, line.quantity, line.weight, line.pieces,
            line.received_quantity, line.received_weight,
        ) for line in transfer_return.lines),
    )


class _ReturnBase:
    def __init__(self, transfer_repository: StockTransferRepository,
                 return_repository: TransferReturnRepository,
                 authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._transfers = transfer_repository
        self._returns = return_repository
        self._authorization = authorization
        self._events = event_sink

    def _load(self, transfer_id: str, return_id: str) -> tuple[StockTransfer, TransferReturn]:
        transfer = self._transfers.get(transfer_id)
        transfer_return = self._returns.get(return_id)
        if transfer is None or transfer_return is None or transfer_return.transfer_id != transfer_id:
            raise TransferNotFoundError("Transfer return not found")
        return transfer, transfer_return

    def _collect(self, event_name: str, operation_id: str, transfer_id: str,
                 user_id: str, return_id: str) -> None:
        if self._events is not None:
            self._events.collect(event_payload(
                event_name, operation_id=operation_id, entity_id=transfer_id,
                user_id=user_id, return_id=return_id,
            ))


class CreateTransferReturnUseCase(_ReturnBase):
    def __init__(self, transfer_repository: StockTransferRepository,
                 return_repository: TransferReturnRepository,
                 authorization: TransferAuthorizationPolicy,
                 number_generator: TransferReturnNumberGenerator,
                 event_sink: TransferEventSink | None = None) -> None:
        super().__init__(transfer_repository, return_repository, authorization, event_sink)
        self._numbers = number_generator

    def execute(self, command: CreateTransferReturnCommand) -> TransferReturnDTO:
        if self._returns.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer return creation operation already exists")
        transfer = self._transfers.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        self._authorization.require(
            user_id=command.requested_by_user_id,
            permission_code=TransferPermissions.RETURN_CREATE,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        received = {line.id: line for line in transfer.lines}
        if not command.lines or not {line.transfer_line_id for line in command.lines}.issubset(received):
            raise TransferNotFoundError("Return references an unknown transfer line")
        lines: list[TransferReturnLine] = []
        for requested in command.lines:
            source = received[requested.transfer_line_id]
            line = TransferReturnLine(
                transfer_line_id=requested.transfer_line_id,
                quantity=requested.quantity, weight=requested.weight,
                pieces=requested.pieces, lot_id=requested.lot_id,
            )
            if line.quantity > source.received_quantity or line.weight > source.received_weight:
                raise TransferOverReceiptError("Return exceeds physically received merchandise")
            lines.append(line)
        transfer_return = TransferReturn(
            transfer_id=transfer.id, return_number=self._numbers.next_return_number(),
            reason=command.reason, source_node=transfer.destination_node,
            destination_node=transfer.origin_node,
            requested_by_user_id=command.requested_by_user_id,
            request_operation_id=command.operation_id, lines=lines,
        )
        self._returns.save(transfer_return)
        self._returns.record_operation(
            return_id=transfer_return.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_RETURN_CREATED",
            actor_id=command.requested_by_user_id,
        )
        self._collect(TransferEvents.RETURN_CREATED, command.operation_id, transfer.id,
                      command.requested_by_user_id, transfer_return.id)
        return _dto(transfer_return)


class ApproveTransferReturnUseCase(_ReturnBase):
    def execute(self, command: ApproveTransferReturnCommand) -> TransferReturnDTO:
        if self._returns.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer return approval operation already exists")
        transfer, transfer_return = self._load(command.transfer_id, command.return_id)
        self._authorization.require(
            user_id=command.approved_by_user_id,
            permission_code=TransferPermissions.RETURN_APPROVE,
            branch_id=transfer_return.source_node.branch_id,
            warehouse_id=transfer_return.source_node.warehouse_id,
            location_id=transfer_return.source_node.location_id,
        )
        transfer_return.approve(command.approved_by_user_id)
        transfer.begin_return()
        self._transfers.save(transfer)
        self._returns.save(transfer_return)
        self._returns.record_operation(
            return_id=transfer_return.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_RETURN_APPROVED",
            actor_id=command.approved_by_user_id,
        )
        return _dto(transfer_return)


class DispatchTransferReturnUseCase(_ReturnBase):
    def __init__(self, transfer_repository: StockTransferRepository,
                 return_repository: TransferReturnRepository,
                 inventory_gateway: InventoryTransferGateway,
                 authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        super().__init__(transfer_repository, return_repository, authorization, event_sink)
        self._inventory = inventory_gateway

    def execute(self, command: DispatchTransferReturnCommand) -> TransferReturnDTO:
        if self._returns.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer return dispatch operation already exists")
        transfer, transfer_return = self._load(command.transfer_id, command.return_id)
        if transfer.cold_chain_required and command.temperature is None:
            raise ValueError("Cold-chain return dispatch requires temperature")
        self._authorization.require(
            user_id=command.dispatched_by_user_id,
            permission_code=TransferPermissions.RETURN_DISPATCH,
            branch_id=transfer_return.source_node.branch_id,
            warehouse_id=transfer_return.source_node.warehouse_id,
            location_id=transfer_return.source_node.location_id,
        )
        transfer_return.dispatch(command.dispatched_by_user_id)
        custody = TransferReturnCustodyEvent(
            return_id=transfer_return.id, event_type="RETURN_RELEASED",
            delivered_by_user_id=command.dispatched_by_user_id,
            received_by_user_id=command.custody_received_by_user_id,
            location_id=transfer_return.source_node.location_id,
            evidence_reference=command.evidence_reference, temperature=command.temperature,
        )
        self._inventory.dispatch_return(
            transfer_return=transfer_return, operation_id=command.operation_id,
            actor_id=command.dispatched_by_user_id)
        transfer_return.mark_in_transit()
        self._returns.save(transfer_return, custody)
        self._returns.record_operation(
            return_id=transfer_return.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_RETURN_DISPATCHED",
            actor_id=command.dispatched_by_user_id,
        )
        self._collect(TransferEvents.IN_TRANSIT, command.operation_id, transfer.id,
                      command.dispatched_by_user_id, transfer_return.id)
        return _dto(transfer_return, custody)


class ReceiveTransferReturnUseCase(_ReturnBase):
    def __init__(self, transfer_repository: StockTransferRepository,
                 return_repository: TransferReturnRepository,
                 inventory_gateway: InventoryTransferGateway,
                 authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        super().__init__(transfer_repository, return_repository, authorization, event_sink)
        self._inventory = inventory_gateway

    def execute(self, command: ReceiveTransferReturnCommand) -> TransferReturnDTO:
        if self._returns.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer return receipt operation already exists")
        transfer, transfer_return = self._load(command.transfer_id, command.return_id)
        if transfer.cold_chain_required and command.temperature is None:
            raise ValueError("Cold-chain return receipt requires temperature")
        self._authorization.require(
            user_id=command.received_by_user_id,
            permission_code=TransferPermissions.RECEIVE,
            branch_id=transfer_return.destination_node.branch_id,
            warehouse_id=transfer_return.destination_node.warehouse_id,
            location_id=transfer_return.destination_node.location_id,
        )
        values = {line.return_line_id: (line.quantity, line.weight) for line in command.lines}
        if len(values) != len(command.lines):
            raise ValueError("Return receipt contains duplicate lines")
        transfer_return.receive(command.received_by_user_id, values)
        custody = TransferReturnCustodyEvent(
            return_id=transfer_return.id, event_type="RETURN_ORIGIN_RECEIVED",
            delivered_by_user_id=command.custody_delivered_by_user_id,
            received_by_user_id=command.received_by_user_id,
            location_id=transfer_return.destination_node.location_id,
            evidence_reference=command.evidence_reference, temperature=command.temperature,
        )
        self._inventory.receive_return(
            transfer_return=transfer_return, operation_id=command.operation_id,
            actor_id=command.received_by_user_id)
        transfer_return.complete()
        transfer.complete_return()
        self._transfers.save(transfer)
        self._returns.save(transfer_return, custody)
        self._returns.record_operation(
            return_id=transfer_return.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_RETURN_COMPLETED",
            actor_id=command.received_by_user_id,
        )
        self._collect(TransferEvents.RETURN_COMPLETED, command.operation_id, transfer.id,
                      command.received_by_user_id, transfer_return.id)
        return _dto(transfer_return, custody)
