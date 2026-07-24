"""TRF-5 request use cases: create, edit, submit, and priority handling."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferNotFoundError
from backend.domain.transfers.policies.segregation_of_duties_policy import TransferSegregationOfDutiesPolicy
from backend.domain.transfers.repository_ports import StockTransferRepository
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    CreateTransferRequestCommand,
    EditTransferRequestCommand,
    RejectTransferRequestCommand,
    SubmitTransferRequestCommand,
    TransferApprovalLineCommand,
    TransferRequestLineCommand,
)
from ..dto.transfer_request_dto import TransferRequestDTO, TransferRequestLineDTO
from ..permissions import TransferPermissions


class TransferRequestNumberGenerator(Protocol):
    def next_transfer_number(self) -> str: ...


class TransferEventSink(Protocol):
    def collect(self, payload: dict[str, object]) -> None: ...


class StaticTransferRequestNumberGenerator:
    def next_transfer_number(self) -> str:
        return "TRF-2026-000001"


def _line_from_command(command: TransferRequestLineCommand) -> StockTransferLine:
    return StockTransferLine(
        product_id=command.product_id,
        unit_id=command.unit_id,
        requested_quantity=command.requested_quantity,
        requested_weight=command.requested_weight,
        pieces=command.pieces,
        lot_required=command.lot_required,
        quality_required=command.quality_required,
        temperature_required=command.temperature_required,
        notes=command.notes,
    )


def _dto(transfer: StockTransfer) -> TransferRequestDTO:
    return TransferRequestDTO(
        transfer_id=transfer.id,
        transfer_number=transfer.transfer_number,
        status=transfer.status.value,
        priority=transfer.priority,
        requested_by_user_id=transfer.requested_by_user_id,
        origin_branch_id=transfer.origin_node.branch_id,
        origin_warehouse_id=transfer.origin_node.warehouse_id,
        origin_location_id=transfer.origin_node.location_id,
        destination_branch_id=transfer.destination_node.branch_id,
        destination_warehouse_id=transfer.destination_node.warehouse_id,
        destination_location_id=transfer.destination_node.location_id,
        lines=tuple(
            TransferRequestLineDTO(
                line_id=line.id,
                product_id=line.product_id,
                unit_id=line.unit_id,
                requested_quantity=line.requested_quantity,
                requested_weight=line.requested_weight,
                pieces=line.pieces,
                notes=line.notes,
            )
            for line in transfer.lines
        ),
    )


def _record_operation(repository: StockTransferRepository, *, transfer_id: str,
                      operation_id: str, operation_type: str) -> None:
    repository.record_operation(
        transfer_id=transfer_id,
        operation_id=operation_id,
        operation_type=operation_type,
    )


def _approved_values(lines: tuple[TransferApprovalLineCommand, ...]) -> dict[str, tuple[object, object]]:
    approved = {
        line.transfer_line_id: (line.approved_quantity, line.approved_weight)
        for line in lines
    }
    if len(approved) != len(lines):
        raise ValueError("Approval command contains duplicated transfer lines")
    return approved


def _is_partial_approval(transfer: StockTransfer, lines: tuple[TransferApprovalLineCommand, ...]) -> bool:
    if not lines:
        return False
    approved_by_line = _approved_values(lines)
    transfer_line_ids = {line.id for line in transfer.lines}
    if not set(approved_by_line).issubset(transfer_line_ids):
        raise ValueError("Approval command references a line outside this transfer")
    if set(approved_by_line) != transfer_line_ids:
        return True
    for line in transfer.lines:
        quantity, weight = approved_by_line[line.id]
        if Decimal(str(quantity)) != line.requested_quantity or Decimal(str(weight)) != line.requested_weight:
            return True
    return False


class CreateTransferRequestUseCase:
    def __init__(
        self,
        repository: StockTransferRepository,
        authorization: TransferAuthorizationPolicy,
        number_generator: TransferRequestNumberGenerator,
        event_sink: TransferEventSink | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._number_generator = number_generator
        self._event_sink = event_sink

    def execute(self, command: CreateTransferRequestCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer request operation was already applied")
        self._authorization.require(
            user_id=command.requested_by_user_id,
            permission_code=TransferPermissions.REQUEST_CREATE,
            branch_id=command.origin_node.branch_id,
            warehouse_id=command.origin_node.warehouse_id,
            location_id=command.origin_node.location_id,
        )
        transfer = StockTransfer(
            transfer_number=self._number_generator.next_transfer_number(),
            transfer_type=command.transfer_type,
            origin_node=command.origin_node,
            destination_node=command.destination_node,
            requested_by_user_id=command.requested_by_user_id,
            operation_id=command.operation_id,
            lines=[_line_from_command(line) for line in command.lines],
            priority=command.priority,
            source_channel=command.source_channel,
            source_reference_id=command.source_reference_id,
            blind_receipt_required=command.blind_receipt_required,
            transport_required=command.transport_required,
            cold_chain_required=command.cold_chain_required,
        )
        transfer.validate_priority()
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_REQUEST_CREATE",
        )
        self._collect(TransferEvents.REQUEST_CREATED, command.operation_id, transfer.id, command.requested_by_user_id)
        return _dto(transfer)

    def _collect(self, event_name: str, operation_id: str, transfer_id: str, user_id: str) -> None:
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(event_name, operation_id=operation_id, entity_id=transfer_id, user_id=user_id))


class EditTransferRequestUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._event_sink = event_sink

    def execute(self, command: EditTransferRequestCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer request edit operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer request not found")
        self._authorization.require(
            user_id=command.edited_by_user_id,
            permission_code=TransferPermissions.REQUEST_EDIT,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        transfer.edit_request(
            lines=[_line_from_command(line) for line in command.lines],
            priority=command.priority,
            source_reference_id=command.source_reference_id,
        )
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_REQUEST_EDIT",
        )
        return _dto(transfer)


class SubmitTransferRequestUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._event_sink = event_sink

    def execute(self, command: SubmitTransferRequestCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer request submit operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer request not found")
        self._authorization.require(
            user_id=command.submitted_by_user_id,
            permission_code=TransferPermissions.REQUEST_SUBMIT,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        transfer.submit()
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_REQUEST_SUBMIT",
        )
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                TransferEvents.REQUEST_SUBMITTED,
                operation_id=command.operation_id,
                entity_id=transfer.id,
                user_id=command.submitted_by_user_id,
            ))
        return _dto(transfer)


class ApproveTransferRequestUseCase:
    def __init__(
        self,
        repository: StockTransferRepository,
        authorization: TransferAuthorizationPolicy,
        segregation: TransferSegregationOfDutiesPolicy | None = None,
        event_sink: TransferEventSink | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._segregation = segregation or TransferSegregationOfDutiesPolicy()
        self._event_sink = event_sink

    def execute(self, command: ApproveTransferRequestCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer approval operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer request not found")
        partial = _is_partial_approval(transfer, command.lines)
        self._authorization.require(
            user_id=command.approved_by_user_id,
            permission_code=TransferPermissions.PARTIAL_APPROVE if partial else TransferPermissions.APPROVE,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        self._segregation.requester_cannot_approve(
            transfer.requested_by_user_id,
            command.approved_by_user_id,
            elevated=transfer.priority in {"URGENT", "EMERGENCY"},
        )
        transfer.approve(command.approved_by_user_id, _approved_values(command.lines) if command.lines else None)
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_REQUEST_APPROVE",
        )
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                TransferEvents.APPROVED,
                operation_id=command.operation_id,
                entity_id=transfer.id,
                user_id=command.approved_by_user_id,
                partial=partial,
                reason=command.reason,
            ))
        return _dto(transfer)


class RejectTransferRequestUseCase:
    def __init__(self, repository: StockTransferRepository, authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._repository = repository
        self._authorization = authorization
        self._event_sink = event_sink

    def execute(self, command: RejectTransferRequestCommand) -> TransferRequestDTO:
        if self._repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer rejection operation was already applied")
        transfer = self._repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer request not found")
        self._authorization.require(
            user_id=command.rejected_by_user_id,
            permission_code=TransferPermissions.REJECT,
            branch_id=transfer.origin_node.branch_id,
            warehouse_id=transfer.origin_node.warehouse_id,
            location_id=transfer.origin_node.location_id,
        )
        transfer.reject()
        self._repository.save(transfer)
        _record_operation(
            self._repository,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_REQUEST_REJECT",
        )
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                TransferEvents.REJECTED,
                operation_id=command.operation_id,
                entity_id=transfer.id,
                user_id=command.rejected_by_user_id,
                reason=command.reason,
            ))
        return _dto(transfer)
