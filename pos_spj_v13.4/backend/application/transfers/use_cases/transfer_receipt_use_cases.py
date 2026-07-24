"""TRF-11 total, partial, cumulative, QR and offline receipt workflow."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Protocol

from backend.domain.transfers.entities.stock_transfer import TransferReceipt, TransferReceiptLine
from backend.domain.transfers.enums import ColdChainStatus, ReceiptQualityStatus, TransferStatus
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import (
    DuplicateOperationError,
    SegregationOfDutiesError,
    TransferNotFoundError,
    TransferOverReceiptError,
    TransferReceiptNotAllowedError,
)
from backend.domain.transfers.policies.cold_chain_transfer_policy import (
    ColdChainAssessment,
    ColdChainTransferPolicy,
    ProductTransferProfile,
)
from backend.domain.transfers.repository_ports import (
    InventoryTransferGateway,
    StockTransferRepository,
    TransferReceiptRepository,
    TransferShipmentRepository,
)
from ..authorization import TransferAuthorizationPolicy
from ..commands.transfer_request_commands import ConfirmTransferReceiptCommand
from ..dto.receipt_dto import TransferReceiptDTO, TransferReceiptLineDTO
from ..permissions import TransferPermissions
from .transfer_request_use_cases import TransferEventSink


class TransferReceiptQrValidator(Protocol):
    def validate(self, *, payload: str, transfer_id: str, shipment_id: str) -> None: ...


class ProductTransferProfileQueryService(Protocol):
    def get_transfer_profile(self, product_id: str) -> ProductTransferProfile: ...


class TransferQualityGateway(Protocol):
    def request_inspection(self, *, transfer_id: str, shipment_id: str,
                           receipt_id: str, transfer_line_id: str, product_id: str,
                           lot_id: str | None, reason: str | None,
                           operation_id: str) -> None: ...


def _decimal(value: Decimal | str | int) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Transfer receipt values must use Decimal, string, or integer")
    return value if isinstance(value, Decimal) else Decimal(str(value))


class ConfirmTransferReceiptUseCase:
    def __init__(
        self,
        transfer_repository: StockTransferRepository,
        shipment_repository: TransferShipmentRepository,
        receipt_repository: TransferReceiptRepository,
        inventory_gateway: InventoryTransferGateway,
        authorization: TransferAuthorizationPolicy,
        qr_validator: TransferReceiptQrValidator | None = None,
        event_sink: TransferEventSink | None = None,
        product_profiles: ProductTransferProfileQueryService | None = None,
        cold_chain_policy: ColdChainTransferPolicy | None = None,
        quality_gateway: TransferQualityGateway | None = None,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        self._transfer_repository = transfer_repository
        self._shipment_repository = shipment_repository
        self._receipt_repository = receipt_repository
        self._inventory_gateway = inventory_gateway
        self._authorization = authorization
        self._qr_validator = qr_validator
        self._event_sink = event_sink
        self._product_profiles = product_profiles
        self._cold_chain_policy = cold_chain_policy
        self._quality_gateway = quality_gateway
        self._today_provider = today_provider

    def execute(self, command: ConfirmTransferReceiptCommand) -> TransferReceiptDTO:
        if self._receipt_repository.operation_exists(command.operation_id):
            raise DuplicateOperationError("Transfer receipt operation was already applied")
        transfer = self._transfer_repository.get(command.transfer_id)
        if transfer is None:
            raise TransferNotFoundError("Transfer not found")
        shipment = self._shipment_repository.get(command.shipment_id)
        if shipment is None or shipment.transfer_id != transfer.id:
            raise TransferNotFoundError("Shipment does not belong to this transfer")
        if shipment.dispatched_by_user_id == command.received_by_user_id:
            raise SegregationOfDutiesError("Dispatcher cannot confirm destination receipt")
        if not command.lines:
            raise ValueError("Receipt requires at least one observed line")
        line_ids = [line.transfer_line_id for line in command.lines]
        if len(set(line_ids)) != len(line_ids) or not set(line_ids).issubset(
            {line.id for line in transfer.lines}
        ):
            raise ValueError("Receipt contains duplicate or unknown transfer lines")
        shipped = {line.transfer_line_id: line for line in shipment.lines}
        if not set(line_ids).issubset(shipped):
            raise TransferOverReceiptError("Receipt references a line outside this shipment")
        received = self._receipt_repository.received_totals(shipment.id)
        remaining = {
            line_id: (
                line.quantity - _decimal(received.get(line_id, (0, 0))[0]),
                line.weight - _decimal(received.get(line_id, (0, 0))[1]),
            )
            for line_id, line in shipped.items()
        }
        for line in command.lines:
            quantity, weight = remaining[line.transfer_line_id]
            if (_decimal(line.observed_quantity) > quantity
                    or _decimal(line.observed_weight) > weight):
                raise TransferOverReceiptError("Receipt exceeds shipment balance")
        partial = set(line_ids) != set(shipped) or any(
            (_decimal(line.observed_quantity), _decimal(line.observed_weight))
            != remaining[line.transfer_line_id]
            for line in command.lines
        )
        self._authorization.require(
            user_id=command.received_by_user_id,
            permission_code=(TransferPermissions.PARTIAL_RECEIVE if partial
                             else TransferPermissions.RECEIVE),
            branch_id=transfer.destination_node.branch_id,
            warehouse_id=transfer.destination_node.warehouse_id,
            location_id=transfer.destination_node.location_id,
        )
        if command.qr_payload is not None:
            if self._qr_validator is None:
                raise ValueError("QR receipt validator is not configured")
            self._qr_validator.validate(payload=command.qr_payload,
                                        transfer_id=transfer.id,
                                        shipment_id=command.shipment_id)
        transfer_lines = {line.id: line for line in transfer.lines}
        assessments: dict[str, tuple[ProductTransferProfile, ColdChainAssessment]] = {}
        for observed in command.lines:
            transfer_line = transfer_lines[observed.transfer_line_id]
            requires_profile = (transfer.cold_chain_required or transfer_line.lot_required
                                or transfer_line.quality_required
                                or transfer_line.temperature_required
                                or _decimal(observed.observed_pieces) > 0)
            if not requires_profile:
                continue
            if self._product_profiles is None or self._cold_chain_policy is None:
                raise TransferReceiptNotAllowedError("Product and cold-chain profiles are required")
            profile = self._product_profiles.get_transfer_profile(transfer_line.product_id)
            if profile.product_id != transfer_line.product_id:
                raise TransferReceiptNotAllowedError("Product profile identity mismatch")
            if profile.lot_required and not observed.lot_id:
                raise TransferReceiptNotAllowedError("Lot-controlled receipt requires a lot")
            if profile.catch_weight and (
                _decimal(observed.observed_pieces) <= 0 or _decimal(observed.observed_weight) <= 0
            ):
                raise TransferReceiptNotAllowedError("Catch-weight receipt requires pieces and weight")
            assessment = self._cold_chain_policy.evaluate(
                profile=profile, temperature=observed.temperature,
                expires_on=observed.expires_on, observed_on=self._today_provider())
            if assessment.requires_quality_inspection and self._quality_gateway is None:
                raise TransferReceiptNotAllowedError("Quality gateway is required for blocked merchandise")
            assessments[observed.transfer_line_id] = (profile, assessment)
        sync_status = "PENDING" if command.offline else "CONFIRMED"
        receipt = TransferReceipt(
            shipment_id=command.shipment_id,
            received_by_user_id=command.received_by_user_id,
            operation_id=command.operation_id,
            lines=tuple(TransferReceiptLine(
                transfer_line_id=line.transfer_line_id,
                observed_quantity=line.observed_quantity,
                observed_weight=line.observed_weight,
                accepted=line.accepted,
                lot_id=line.lot_id,
                observed_pieces=line.observed_pieces,
                temperature=line.temperature,
                expires_on=line.expires_on,
                cold_chain_status=(assessments[line.transfer_line_id][1].cold_chain_status
                                   if line.transfer_line_id in assessments else ColdChainStatus.COMPLIANT),
                quality_status=(assessments[line.transfer_line_id][1].quality_status
                                if line.transfer_line_id in assessments else ReceiptQualityStatus.AVAILABLE),
            ) for line in command.lines),
            device_id=command.device_id,
            local_sequence=command.local_sequence,
            sync_status=sync_status,
            qr_reference=command.qr_payload,
        )
        differences = tuple(transfer.receive(receipt))
        self._inventory_gateway.receive(
            transfer=transfer,
            receipt=receipt,
            operation_id=command.operation_id,
            actor_id=command.received_by_user_id,
        )
        self._transfer_repository.save(transfer)
        self._receipt_repository.save(receipt, differences)
        self._receipt_repository.record_operation(
            receipt_id=receipt.id,
            transfer_id=transfer.id,
            operation_id=command.operation_id,
            operation_type="TRANSFER_RECEIPT",
            device_id=command.device_id,
            local_sequence=command.local_sequence,
            sync_status=sync_status,
        )
        for line in receipt.lines:
            if line.transfer_line_id in assessments:
                profile, assessment = assessments[line.transfer_line_id]
                if assessment.requires_quality_inspection:
                    self._quality_gateway.request_inspection(
                        transfer_id=transfer.id, shipment_id=receipt.shipment_id,
                        receipt_id=receipt.id, transfer_line_id=line.transfer_line_id,
                        product_id=profile.product_id, lot_id=line.lot_id,
                        reason=assessment.reason, operation_id=command.operation_id,
                    )
        event_name = (TransferEvents.RECEIVED if transfer.status is TransferStatus.RECEIVED
                      else TransferEvents.PARTIALLY_RECEIVED)
        self._collect(event_name, command, receipt.id, sync_status=sync_status)
        if differences:
            self._collect(TransferEvents.DIFFERENCE_DETECTED, command, receipt.id,
                          difference_ids=tuple(item.id for item in differences))
        return TransferReceiptDTO(
            receipt_id=receipt.id,
            transfer_id=transfer.id,
            shipment_id=receipt.shipment_id,
            transfer_status=transfer.status.value,
            sync_status=receipt.sync_status,
            difference_ids=tuple(item.id for item in differences),
            lines=tuple(TransferReceiptLineDTO(
                item.transfer_line_id, item.observed_quantity,
                item.observed_weight, item.accepted, item.observed_pieces,
                item.temperature, item.expires_on, item.cold_chain_status.value,
                item.quality_status.value,
            ) for item in receipt.lines),
        )

    def _collect(self, event_name: str, command: ConfirmTransferReceiptCommand,
                 receipt_id: str, **extra: object) -> None:
        if self._event_sink is not None:
            self._event_sink.collect(event_payload(
                event_name,
                operation_id=command.operation_id,
                entity_id=command.transfer_id,
                user_id=command.received_by_user_id,
                shipment_id=command.shipment_id,
                receipt_id=receipt_id,
                **extra,
            ))
