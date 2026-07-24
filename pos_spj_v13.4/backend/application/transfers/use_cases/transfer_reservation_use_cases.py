"""TRF-7 reservation and FEFO lot allocation use cases."""
from __future__ import annotations

from typing import Protocol

from backend.domain.transfers.entities.stock_transfer import StockTransfer, ZERO
from backend.domain.transfers.enums import TransferStatus
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferLotAllocationError, TransferNotFoundError
from backend.domain.transfers.policies.lot_allocation_policy import (
    LotAllocationCandidate,
    LotAllocationPolicy,
    TransferLotAllocation,
)
from backend.domain.transfers.repository_ports import InventoryTransferGateway, StockTransferRepository
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import ReserveTransferInventoryCommand, ReserveTransferLineCommand
from ..dto.transfer_request_dto import TransferRequestDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink, _dto, _record_operation


class TransferLotAvailabilityReadPort(Protocol):
    def available_lots_for_transfer_line(
        self,
        *,
        transfer: StockTransfer,
        transfer_line_id: str,
    ) -> tuple[LotAllocationCandidate, ...]: ...


def _reserved_values(command_lines: tuple[ReserveTransferLineCommand, ...],
                     transfer: StockTransfer) -> dict[str, tuple[object, object]]:
    if not command_lines:
        return {line.id: (line.approved_quantity, line.approved_weight) for line in transfer.lines}
    values = {line.transfer_line_id: (line.reserved_quantity, line.reserved_weight) for line in command_lines}
    if len(values) != len(command_lines):
        raise ValueError("Reservation command contains duplicated transfer lines")
    transfer_line_ids = {line.id for line in transfer.lines}
    if not set(values).issubset(transfer_line_ids):
        raise ValueError("Reservation command references a line outside this transfer")
    return values


class ReserveTransferInventoryUseCase:
    def __init__(
        self,
        repository: StockTransferRepository,
        inventory_gateway: InventoryTransferGateway,
        authorization: TransferAuthorizationPolicy,
        lot_availability: TransferLotAvailabilityReadPort | None = None,
        lot_policy: LotAllocationPolicy | None = None,
        event_sink: TransferEventSink | None = None,
    ) -> None:
        self._repository = repository
        self._inventory_gateway = inventory_gateway
        self._authorization = authorization
        self._lot_availability = lot_availability
        self._lot_policy = lot_policy or LotAllocationPolicy()
        self._event_sink = event_sink

    def execute(self, command: ReserveTransferInventoryCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer reservation operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer request not found")
        self._authorization.require(
            user_id=command.reserved_by_user_id,
            permission_code=TransferPermissions.RESERVE,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        reserved = _reserved_values(command.lines, transfer)
        allocations = self._allocate_if_required(command, transfer, reserved)
        if transfer.status is TransferStatus.APPROVED:
            transfer.begin_reservation()
        transfer.reserve(reserved)
        self._inventory_gateway.reserve(
            transfer=transfer,
            operation_id=command.operation_id,
            actor_id=command.reserved_by_user_id,
            allocations=allocations,
        )
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_RESERVE",
        )
        self._collect(TransferEvents.RESERVED, command.operation_id, transfer.id, command.reserved_by_user_id)
        if allocations:
            self._collect(TransferEvents.ALLOCATED, command.operation_id, transfer.id,
                          command.reserved_by_user_id, allocation_count=len(allocations))
        return _dto(transfer)

    def _allocate_if_required(
        self,
        command: ReserveTransferInventoryCommand,
        transfer: StockTransfer,
        reserved: dict[str, tuple[object, object]],
    ) -> tuple[TransferLotAllocation, ...]:
        if not command.allocate_lots_fefo:
            return ()
        if self._lot_availability is None:
            raise TransferLotAllocationError("FEFO allocation requires a lot availability read port")
        allocations: list[TransferLotAllocation] = []
        lines_by_id = {line.id: line for line in transfer.lines}
        for line_id, (quantity, weight) in reserved.items():
            if quantity == ZERO:
                continue
            line = lines_by_id[line_id]
            allocations.extend(self._lot_policy.allocate_fefo(
                transfer_line_id=line.id,
                product_id=line.product_id,
                required_quantity=quantity,
                required_weight=weight,
                candidates=self._lot_availability.available_lots_for_transfer_line(
                    transfer=transfer,
                    transfer_line_id=line.id,
                ),
            ))
        return tuple(allocations)

    def _collect(self, event_name: str, operation_id: str, transfer_id: str, user_id: str,
                 **extra: object) -> None:
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                event_name,
                operation_id=operation_id,
                entity_id=transfer_id,
                user_id=user_id,
                **extra,
            ))
