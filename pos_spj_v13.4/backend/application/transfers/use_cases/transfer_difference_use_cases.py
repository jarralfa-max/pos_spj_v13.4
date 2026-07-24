"""TRF-13 detection, review, evidence and authorized discrepancy resolution."""
from __future__ import annotations

from backend.domain.transfers.entities.stock_transfer import (
    TransferDifference,
    TransferDifferenceResolution,
)
from backend.domain.transfers.enums import DifferenceResolutionType
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import (
    DuplicateOperationError,
    SegregationOfDutiesError,
    TransferNotFoundError,
)
from backend.domain.transfers.policies.transfer_difference_policy import TransferDifferencePolicy
from backend.domain.transfers.repository_ports import StockTransferRepository, TransferDifferenceRepository
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import (
    DetectTransferDifferenceCommand,
    ResolveTransferDifferenceCommand,
    ReviewTransferDifferenceCommand,
)
from ..dto.difference_dto import TransferDifferenceDTO, TransferDifferenceResolutionDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink


def _dto(transfer_id: str, difference: TransferDifference) -> TransferDifferenceDTO:
    return TransferDifferenceDTO(
        difference_id=difference.id, transfer_id=transfer_id,
        transfer_line_id=difference.transfer_line_id,
        difference_type=difference.difference_type.value, status=difference.status.value,
        severity=difference.severity, expected_quantity=difference.expected_quantity,
        actual_quantity=difference.actual_quantity, quantity_difference=difference.quantity_delta,
        expected_weight=difference.expected_weight, actual_weight=difference.actual_weight,
        weight_difference=difference.weight_delta, evidence=difference.evidence,
    )


class DetectTransferDifferencesUseCase:
    def __init__(self, transfer_repository: StockTransferRepository,
                 difference_repository: TransferDifferenceRepository,
                 authorization: TransferAuthorizationPolicy,
                 tolerance_policy: TransferDifferencePolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._transfers = transfer_repository
        self._differences = difference_repository
        self._authorization = authorization
        self._policy = tolerance_policy
        self._events = event_sink

    def execute(self, command: DetectTransferDifferenceCommand) -> tuple[TransferDifferenceDTO, ...]:
        if self._differences.operation_exists(command.operation_id):
            raise DuplicateOperationError("Difference detection operation already exists")
        transfer = self._transfers.get(command.transfer_id)
        if transfer is None or command.transfer_line_id not in {line.id for line in transfer.lines}:
            raise TransferNotFoundError("Transfer line not found")
        self._authorization.require(
            user_id=command.detected_by_user_id,
            permission_code=TransferPermissions.DIFFERENCE_REVIEW,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        types = ((command.reported_type,) if command.reported_type is not None else
                 self._policy.classify(
                     expected_quantity=command.expected_quantity,
                     actual_quantity=command.actual_quantity,
                     expected_weight=command.expected_weight,
                     actual_weight=command.actual_weight))
        differences = tuple(TransferDifference(
            transfer_line_id=command.transfer_line_id,
            difference_type=difference_type,
            expected_quantity=command.expected_quantity,
            actual_quantity=command.actual_quantity,
            expected_weight=command.expected_weight,
            actual_weight=command.actual_weight,
            severity=command.severity,
            responsible_stage=command.responsible_stage,
            evidence=command.evidence,
            detected_by_user_id=command.detected_by_user_id,
        ) for difference_type in types)
        if not differences:
            return ()
        transfer.register_difference()
        self._transfers.save(transfer)
        self._differences.save_all(transfer.id, differences)
        self._differences.record_operation(
            difference_id=differences[0].id, transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_DIFFERENCE_DETECTED",
            actor_id=command.detected_by_user_id,
        )
        if self._events is not None:
            self._events.collect(event_payload(
                TransferEvents.DIFFERENCE_DETECTED, operation_id=command.operation_id,
                entity_id=transfer.id, user_id=command.detected_by_user_id,
                difference_ids=tuple(item.id for item in differences),
            ))
        return tuple(_dto(transfer.id, item) for item in differences)


class ReviewTransferDifferenceUseCase:
    def __init__(self, transfer_repository: StockTransferRepository,
                 difference_repository: TransferDifferenceRepository,
                 authorization: TransferAuthorizationPolicy) -> None:
        self._transfers = transfer_repository
        self._differences = difference_repository
        self._authorization = authorization

    def execute(self, command: ReviewTransferDifferenceCommand) -> TransferDifferenceDTO:
        if self._differences.operation_exists(command.operation_id):
            raise DuplicateOperationError("Difference review operation already exists")
        transfer = self._transfers.get(command.transfer_id)
        difference = self._differences.get(command.difference_id)
        if (transfer is None or difference is None
                or not self._differences.belongs_to_transfer(command.difference_id, command.transfer_id)):
            raise TransferNotFoundError("Transfer difference not found")
        self._authorization.require(
            user_id=command.reviewed_by_user_id,
            permission_code=TransferPermissions.DIFFERENCE_REVIEW,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        difference.submit_for_review()
        if transfer.status.value == "WITH_DIFFERENCES":
            transfer.mark_pending_resolution()
            self._transfers.save(transfer)
        self._differences.save_all(transfer.id, (difference,))
        self._differences.record_operation(
            difference_id=difference.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_DIFFERENCE_REVIEWED",
            actor_id=command.reviewed_by_user_id)
        return _dto(transfer.id, difference)


class ResolveTransferDifferenceUseCase:
    _ACCEPTANCE_TYPES = {DifferenceResolutionType.ACCEPT_SHORTAGE,
                         DifferenceResolutionType.ACCEPT_OVERAGE}
    _TYPE_RESTRICTIONS = {
        DifferenceResolutionType.ACCEPT_SHORTAGE: "SHORT_QUANTITY",
        DifferenceResolutionType.ACCEPT_OVERAGE: "OVER_QUANTITY",
    }

    def __init__(self, transfer_repository: StockTransferRepository,
                 difference_repository: TransferDifferenceRepository,
                 authorization: TransferAuthorizationPolicy,
                 event_sink: TransferEventSink | None = None) -> None:
        self._transfers = transfer_repository
        self._differences = difference_repository
        self._authorization = authorization
        self._events = event_sink

    def execute(self, command: ResolveTransferDifferenceCommand) -> TransferDifferenceResolutionDTO:
        if self._differences.operation_exists(command.operation_id):
            raise DuplicateOperationError("Difference resolution operation already exists")
        transfer = self._transfers.get(command.transfer_id)
        difference = self._differences.get(command.difference_id)
        if (transfer is None or difference is None
                or not self._differences.belongs_to_transfer(command.difference_id, command.transfer_id)):
            raise TransferNotFoundError("Transfer difference not found")
        permission = (TransferPermissions.DIFFERENCE_ACCEPT
                      if command.resolution_type in self._ACCEPTANCE_TYPES
                      else TransferPermissions.DIFFERENCE_RESOLVE)
        self._authorization.require(
            user_id=command.resolved_by_user_id, permission_code=permission,
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        if (difference.severity == "CRITICAL"
                and difference.detected_by_user_id == command.resolved_by_user_id):
            raise SegregationOfDutiesError("Critical difference requires an independent resolver")
        required_type = self._TYPE_RESTRICTIONS.get(command.resolution_type)
        if required_type is not None and difference.difference_type.value != required_type:
            raise ValueError("Resolution type is incompatible with the detected difference")
        resolution = TransferDifferenceResolution(
            difference_id=difference.id, resolution_type=command.resolution_type,
            resolved_by_user_id=command.resolved_by_user_id,
            operation_id=command.operation_id, reason=command.reason,
            evidence=command.evidence,
        )
        difference.resolve()
        self._differences.save_resolution(difference, resolution)
        self._differences.record_operation(
            difference_id=difference.id, transfer_id=transfer.id,
            operation_id=command.operation_id, operation_type="TRANSFER_DIFFERENCE_RESOLVED",
            actor_id=command.resolved_by_user_id)
        if self._events is not None:
            self._events.collect(event_payload(
                TransferEvents.DIFFERENCE_RESOLVED, operation_id=command.operation_id,
                entity_id=transfer.id, user_id=command.resolved_by_user_id,
                difference_id=difference.id, resolution_id=resolution.id,
                resolution_type=resolution.resolution_type.value,
            ))
        return TransferDifferenceResolutionDTO(
            resolution.id, difference.id, resolution.resolution_type.value,
            difference.status.value, resolution.reason, resolution.evidence,
        )
