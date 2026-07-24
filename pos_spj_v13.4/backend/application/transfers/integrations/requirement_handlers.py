"""Inbound Sales, POS and Production needs mapped to transfer requests only."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.domain.transfers.enums import TransferType
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from ..commands.transfer_request_commands import (
    CreateTransferRequestCommand,
    TransferRequestLineCommand,
)
from ..dto.transfer_request_dto import TransferRequestDTO
from ..use_cases.transfer_request_use_cases import CreateTransferRequestUseCase


class TransferNodeQueryService(Protocol):
    def get_node(self, node_id: str) -> TransferNode: ...


def _decimal(value: object) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError("Transfer requirement values must use decimal strings")
    return Decimal(str(value))


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("Transfer requirement flags must be booleans")
    return value


class TransferRequirementEventHandler:
    EVENT_NAME: str
    TRANSFER_TYPE: TransferType
    SOURCE_CHANNEL: str

    def __init__(self, create_request: CreateTransferRequestUseCase,
                 nodes: TransferNodeQueryService) -> None:
        self._create_request = create_request
        self._nodes = nodes

    def handle(self, event: dict[str, object]) -> TransferRequestDTO:
        if event.get("event_name") != self.EVENT_NAME:
            raise ValueError(f"Unsupported {self.SOURCE_CHANNEL} transfer event")
        lines = tuple(TransferRequestLineCommand(
            product_id=str(line["product_id"]), unit_id=str(line["unit_id"]),
            requested_quantity=_decimal(line["quantity"]),
            requested_weight=_decimal(line.get("weight", "0")),
            pieces=_decimal(line.get("pieces", "0")),
            lot_required=_boolean(line.get("lot_required", False)),
            quality_required=_boolean(line.get("quality_required", False)),
            temperature_required=_boolean(line.get("temperature_required", False)),
        ) for line in event["lines"])
        return self._create_request.execute(CreateTransferRequestCommand(
            requested_by_user_id=str(event["user_id"]),
            operation_id=str(event["operation_id"]),
            transfer_type=self.TRANSFER_TYPE,
            origin_node=self._nodes.get_node(str(event["origin_node_id"])),
            destination_node=self._nodes.get_node(str(event["destination_node_id"])),
            lines=lines, source_channel=self.SOURCE_CHANNEL,
            source_reference_id=str(event["entity_id"]),
            cold_chain_required=_boolean(event.get("cold_chain_required", False)),
        ))


class SalesCustomerOrderTransferHandler(TransferRequirementEventHandler):
    EVENT_NAME = "CUSTOMER_ORDER_REQUIRES_TRANSFER"
    TRANSFER_TYPE = TransferType.CUSTOMER_ORDER_TRANSFER
    SOURCE_CHANNEL = "SALES"


class PosStockReplenishmentHandler(TransferRequirementEventHandler):
    EVENT_NAME = "STOCK_REPLENISHMENT_REQUIRED"
    TRANSFER_TYPE = TransferType.REPLENISHMENT_TRANSFER
    SOURCE_CHANNEL = "POS"


class ProductionMaterialTransferHandler(TransferRequirementEventHandler):
    EVENT_NAME = "PRODUCTION_MATERIAL_TRANSFER_REQUIRED"
    TRANSFER_TYPE = TransferType.PRODUCTION_SUPPLY_TRANSFER
    SOURCE_CHANNEL = "PRODUCTION"
