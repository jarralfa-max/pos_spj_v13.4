"""TRF-10 dispatch, partial shipment, custody and in-transit use cases."""
from __future__ import annotations

from decimal import Decimal

from backend.domain.transfers.entities.transfer_shipment import (
    TransferCustodyEvent,
    TransferShipment,
    TransferShipmentLine,
)
from backend.domain.transfers.enums import TransferStatus
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferNotFoundError
from backend.domain.transfers.repository_ports import (
    InventoryTransferGateway,
    StockTransferRepository,
    TransferShipmentRepository,
)
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import DispatchTransferShipmentCommand
from ..dto.shipment_dto import TransferShipmentDTO, TransferShipmentLineDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink


def _line_values(command: DispatchTransferShipmentCommand) -> tuple[
    dict[str, Decimal | str | int],
    dict[str, Decimal | str | int],
]:
    quantities = {line.transfer_line_id: line.quantity for line in command.lines}
    weights = {line.transfer_line_id: line.weight for line in command.lines}
    if len(quantities) != len(command.lines):
        raise ValueError("Shipment command contains duplicated transfer lines")
    return quantities, weights


class DispatchTransferShipmentUseCase:
    def __init__(
        self,
        transfer_repository: StockTransferRepository,
        shipment_repository: TransferShipmentRepository,
        inventory_gateway: InventoryTransferGateway,
        authorization: TransferAuthorizationPolicy,
        event_sink: TransferEventSink | None = None,
    ) -> None:
        self._transfer_repository = transfer_repository
        self._shipment_repository = shipment_repository
        self._inventory_gateway = inventory_gateway
        self._authorization = authorization
        self._event_sink = event_sink

    def execute(self, command: DispatchTransferShipmentCommand) -> TransferShipmentDTO:
        if self._shipment_repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer dispatch operation was already applied")
        transfer = self._transfer_repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        if transfer.cold_chain_required and command.temperature_at_dispatch is None:
            raise ValueError("Cold-chain dispatch requires temperature capture")
        quantities, weights = _line_values(command)
        transfer_line_ids = {line.id for line in transfer.lines}
        if not set(quantities).issubset(transfer_line_ids):
            raise ValueError("Shipment command references a line outside this transfer")
        partial = set(quantities) != {line.id for line in transfer.lines} or any(
            Decimal(str(quantities.get(line.id, "0"))) < line.dispatchable_quantity
            for line in transfer.lines
        )
        self._authorization.require(
            user_id=command.dispatched_by_user_id,
            permission_code=TransferPermissions.PARTIAL_DISPATCH if partial else TransferPermissions.DISPATCH,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        lines = tuple(
            TransferShipmentLine(line.transfer_line_id, line.quantity, line.weight)
            for line in command.lines
        )
        shipment = TransferShipment(
            transfer_id=transfer.id,
            shipment_number=command.shipment_number,
            dispatched_by_user_id=command.dispatched_by_user_id,
            verified_by_user_id=command.verified_by_user_id,
            lines=lines,
            carrier_id=command.carrier_id,
            vehicle_id=command.vehicle_id,
            driver_id=command.driver_id,
            seal_number=command.seal_number,
            temperature_at_dispatch=command.temperature_at_dispatch,
        )
        transfer.record_dispatch(quantities, weights)
        custody = TransferCustodyEvent(
            shipment_id=shipment.id,
            event_type="ORIGIN_RELEASED",
            delivered_by_user_id=command.dispatched_by_user_id,
            received_by_user_id=command.custody_received_by_user_id,
            location_id=transfer.origin_node.location_id,
            vehicle_id=command.vehicle_id,
            seal_number=command.seal_number,
            evidence_reference=command.evidence_reference,
            temperature=command.temperature_at_dispatch,
        )
        self._inventory_gateway.dispatch(
            transfer=transfer,
            operation_id=command.operation_id,
            actor_id=command.dispatched_by_user_id,
        )
        self._transfer_repository.save(transfer)
        self._shipment_repository.save(shipment, custody)
        self._shipment_repository.record_operation(
            shipment_id=shipment.id,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_DISPATCH",
        )
        self._collect(TransferEvents.DISPATCHED, command.operation_id, transfer.id, command.dispatched_by_user_id,
                      shipment_id=shipment.id, partial=partial)
        if transfer.status is TransferStatus.IN_TRANSIT:
            self._collect(TransferEvents.IN_TRANSIT, command.operation_id, transfer.id,
                          command.dispatched_by_user_id, shipment_id=shipment.id)
        return TransferShipmentDTO(
            shipment_id=shipment.id,
            transfer_id=transfer.id,
            shipment_number=shipment.shipment_number,
            status=shipment.status,
            transfer_status=transfer.status.value,
            seal_number=shipment.seal_number,
            vehicle_id=shipment.vehicle_id,
            custody_event_id=custody.id,
            lines=tuple(TransferShipmentLineDTO(line.transfer_line_id, line.quantity, line.weight) for line in lines),
        )

    def _collect(self, event_name: str, operation_id: str, transfer_id: str, user_id: str,
                 **extra: object) -> None:
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(event_name, operation_id=operation_id,
                                                  entity_id=transfer_id, user_id=user_id, **extra))
