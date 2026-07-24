from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    ConfirmTransferPickingCommand,
    CreateTransferRequestCommand,
    DispatchTransferShipmentCommand,
    DispatchTransferShipmentLineCommand,
    ReserveTransferInventoryCommand,
    StartTransferPickingCommand,
    SubmitTransferRequestCommand,
    TransferPickLineCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_dispatch_use_cases import DispatchTransferShipmentUseCase
from backend.application.transfers.use_cases.transfer_picking_use_cases import (
    ConfirmTransferPickingUseCase,
    StartTransferPickingUseCase,
)
from backend.application.transfers.use_cases.transfer_request_use_cases import (
    ApproveTransferRequestUseCase,
    CreateTransferRequestUseCase,
    SubmitTransferRequestUseCase,
)
from backend.application.transfers.use_cases.transfer_reservation_use_cases import ReserveTransferInventoryUseCase
from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.entities.transfer_shipment import TransferCustodyEvent, TransferShipment
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.exceptions import DuplicateOperationError
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class TransferRepository:
    def __init__(self) -> None:
        self.saved: dict[str, StockTransfer] = {}
        self.operations: set[str] = set()

    def get(self, transfer_id: str) -> StockTransfer | None:
        return self.saved.get(transfer_id)

    def save(self, transfer: StockTransfer) -> None:
        self.saved[transfer.id] = transfer

    def operation_exists(self, operation_id: str) -> bool:
        return operation_id in self.operations

    def record_operation(self, *, transfer_id: str, operation_id: str, operation_type: str) -> None:
        self.operations.add(operation_id)


class ShipmentRepository:
    def __init__(self) -> None:
        self.shipments: dict[str, TransferShipment] = {}
        self.custody: dict[str, TransferCustodyEvent] = {}
        self.operations: set[str] = set()

    def save(self, shipment: TransferShipment, custody_event: TransferCustodyEvent) -> None:
        self.shipments[shipment.id] = shipment
        self.custody[custody_event.id] = custody_event

    def operation_exists(self, operation_id: str) -> bool:
        return operation_id in self.operations

    def record_operation(self, *, shipment_id: str, transfer_id: str,
                         operation_id: str, operation_type: str) -> None:
        assert shipment_id in self.shipments
        assert operation_type == "TRANSFER_DISPATCH"
        self.operations.add(operation_id)


class NumberGenerator:
    def next_transfer_number(self) -> str:
        return "TRF-2026-001100"


class Permissions:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in {
            ("requester", TransferPermissions.REQUEST_CREATE),
            ("requester", TransferPermissions.REQUEST_SUBMIT),
            ("approver", TransferPermissions.APPROVE),
            ("warehouse", TransferPermissions.RESERVE),
            ("picker", TransferPermissions.PICK),
            ("picker", TransferPermissions.PICK_CONFIRM),
            ("dispatcher", TransferPermissions.DISPATCH),
            ("dispatcher", TransferPermissions.PARTIAL_DISPATCH),
        }


class InventoryGateway:
    def __init__(self) -> None:
        self.dispatches: list[dict[str, object]] = []

    def reserve(self, **kwargs) -> None:
        pass

    def dispatch(self, **kwargs) -> None:
        self.dispatches.append(kwargs)


class EventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def collect(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


def _node(branch: str, warehouse: str) -> TransferNode:
    return TransferNode(TransferNodeType.WAREHOUSE, branch, warehouse)


def _auth() -> TransferAuthorizationPolicy:
    return TransferAuthorizationPolicy(Permissions())


def _ready_transfer(repository: TransferRepository) -> tuple[str, str]:
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand(
            "requester",
            "operation-create",
            TransferType.BRANCH_TO_BRANCH,
            _node("branch-a", "warehouse-a"),
            _node("branch-b", "warehouse-b"),
            (TransferRequestLineCommand("product", "unit", Decimal("4"), Decimal("1180.450")),),
        )
    )
    SubmitTransferRequestUseCase(repository, _auth()).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))
    ApproveTransferRequestUseCase(repository, _auth()).execute(
        ApproveTransferRequestCommand(created.transfer_id, "approver", "operation-approve"))
    inventory = InventoryGateway()
    ReserveTransferInventoryUseCase(repository, inventory, _auth()).execute(
        ReserveTransferInventoryCommand(created.transfer_id, "warehouse", "operation-reserve"))
    line_id = repository.get(created.transfer_id).lines[0].id
    StartTransferPickingUseCase(repository, _auth()).execute(
        StartTransferPickingCommand(created.transfer_id, "picker", "operation-picking-start"))
    ConfirmTransferPickingUseCase(repository, _auth()).execute(
        ConfirmTransferPickingCommand(
            created.transfer_id,
            "picker",
            "operation-pick-full",
            (TransferPickLineCommand(line_id, Decimal("4"), Decimal("1180.450"), "barcode", None, "loc-1"),),
        ))
    repository.get(created.transfer_id).ready_to_dispatch()
    return created.transfer_id, line_id


def test_dispatch_full_shipment_creates_custody_and_inventory_in_transit_event():
    transfers = TransferRepository()
    shipments = ShipmentRepository()
    inventory = InventoryGateway()
    events = EventSink()
    transfer_id, line_id = _ready_transfer(transfers)

    dto = DispatchTransferShipmentUseCase(transfers, shipments, inventory, _auth(), events).execute(
        DispatchTransferShipmentCommand(
            transfer_id,
            "dispatcher",
            "verifier",
            "carrier-user",
            "operation-dispatch",
            "SHP-001",
            (DispatchTransferShipmentLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
            vehicle_id="vehicle-1",
            seal_number="seal-ship-1",
            temperature_at_dispatch=Decimal("2.0"),
            evidence_reference="photo-1",
        ))

    assert dto.transfer_status == TransferStatus.IN_TRANSIT.value
    assert dto.seal_number == "seal-ship-1"
    assert inventory.dispatches[0]["operation_id"] == "operation-dispatch"
    custody = next(iter(shipments.custody.values()))
    assert custody.event_type == "ORIGIN_RELEASED"
    assert custody.received_by_user_id == "carrier-user"
    assert custody.temperature == Decimal("2.0")
    assert [event["event_name"] for event in events.events] == ["TRANSFER_DISPATCHED", "TRANSFER_IN_TRANSIT"]


def test_dispatch_partial_shipment_uses_partial_permission_and_status():
    transfers = TransferRepository()
    shipments = ShipmentRepository()
    transfer_id, line_id = _ready_transfer(transfers)

    dto = DispatchTransferShipmentUseCase(transfers, shipments, InventoryGateway(), _auth()).execute(
        DispatchTransferShipmentCommand(
            transfer_id,
            "dispatcher",
            "verifier",
            "carrier-user",
            "operation-dispatch-partial",
            "SHP-002",
            (DispatchTransferShipmentLineCommand(line_id, Decimal("2"), Decimal("590.225")),),
        ))

    assert dto.transfer_status == TransferStatus.PARTIALLY_DISPATCHED.value
    assert dto.lines[0].quantity == Decimal("2")


def test_dispatch_rejects_duplicate_operation_and_non_independent_verifier():
    transfers = TransferRepository()
    shipments = ShipmentRepository()
    transfer_id, line_id = _ready_transfer(transfers)
    shipments.operations.add("operation-dispatch")

    with pytest.raises(DuplicateOperationError):
        DispatchTransferShipmentUseCase(transfers, shipments, InventoryGateway(), _auth()).execute(
            DispatchTransferShipmentCommand(
                transfer_id,
                "dispatcher",
                "verifier",
                "carrier-user",
                "operation-dispatch",
                "SHP-001",
                (DispatchTransferShipmentLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
            ))
    with pytest.raises(ValueError):
        DispatchTransferShipmentUseCase(transfers, ShipmentRepository(), InventoryGateway(), _auth()).execute(
            DispatchTransferShipmentCommand(
                transfer_id,
                "dispatcher",
                "dispatcher",
                "carrier-user",
                "operation-dispatch-2",
                "SHP-001",
                (DispatchTransferShipmentLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
            ))


def test_cold_chain_dispatch_requires_temperature_capture():
    transfers = TransferRepository()
    transfer_id, line_id = _ready_transfer(transfers)
    transfers.get(transfer_id).cold_chain_required = True

    with pytest.raises(ValueError, match="temperature capture"):
        DispatchTransferShipmentUseCase(
            transfers, ShipmentRepository(), InventoryGateway(), _auth()).execute(
                DispatchTransferShipmentCommand(
                    transfer_id, "dispatcher", "verifier", "carrier-user",
                    "cold-dispatch", "SHP-COLD",
                    (DispatchTransferShipmentLineCommand(
                        line_id, Decimal("4"), Decimal("1180.450")),),
                ))
