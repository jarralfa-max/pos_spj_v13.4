from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    ConfirmTransferPickingCommand,
    CreateTransferRequestCommand,
    ReserveTransferInventoryCommand,
    StartTransferPickingCommand,
    SubmitTransferRequestCommand,
    TransferPickLineCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_picking_use_cases import (
    BuildTransferPickingListUseCase,
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
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.exceptions import DuplicateOperationError
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class MemoryRepository:
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
        assert transfer_id in self.saved
        assert operation_type.startswith("TRANSFER_")
        self.operations.add(operation_id)


class NumberGenerator:
    def next_transfer_number(self) -> str:
        return "TRF-2026-000999"


class Permissions:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in {
            ("requester", TransferPermissions.REQUEST_CREATE),
            ("requester", TransferPermissions.REQUEST_SUBMIT),
            ("approver", TransferPermissions.APPROVE),
            ("warehouse", TransferPermissions.RESERVE),
            ("picker", TransferPermissions.PICK),
            ("picker", TransferPermissions.PICK_CONFIRM),
        }


class InventoryGateway:
    def reserve(self, **kwargs) -> None:
        self.last_reservation = kwargs


class BarcodeValidator:
    def __init__(self) -> None:
        self.scans: list[tuple[str | None, str | None, str | None]] = []

    def validate_pick_scan(self, *, transfer: StockTransfer, transfer_line_id: str,
                           barcode: str | None, lot_id: str | None,
                           location_id: str | None) -> None:
        self.scans.append((barcode, lot_id, location_id))


class EventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def collect(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


def _node(branch: str, warehouse: str) -> TransferNode:
    return TransferNode(TransferNodeType.WAREHOUSE, branch, warehouse)


def _auth() -> TransferAuthorizationPolicy:
    return TransferAuthorizationPolicy(Permissions())


def _reserved_transfer(repository: MemoryRepository) -> str:
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand(
            "requester",
            "operation-create",
            TransferType.BRANCH_TO_BRANCH,
            _node("branch-a", "warehouse-a"),
            _node("branch-b", "warehouse-b"),
            (TransferRequestLineCommand(
                "product",
                "unit",
                Decimal("4"),
                Decimal("1180.450"),
                lot_required=True,
            ),),
        )
    )
    SubmitTransferRequestUseCase(repository, _auth()).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))
    ApproveTransferRequestUseCase(repository, _auth()).execute(
        ApproveTransferRequestCommand(created.transfer_id, "approver", "operation-approve"))
    ReserveTransferInventoryUseCase(repository, InventoryGateway(), _auth()).execute(
        ReserveTransferInventoryCommand(created.transfer_id, "warehouse", "operation-reserve"))
    return created.transfer_id


def test_build_and_start_picking_list_from_reserved_transfer():
    repository = MemoryRepository()
    transfer_id = _reserved_transfer(repository)
    events = EventSink()

    picking_list = BuildTransferPickingListUseCase(repository, _auth()).execute(
        transfer_id=transfer_id,
        user_id="picker",
    )
    dto = StartTransferPickingUseCase(repository, _auth(), events).execute(
        StartTransferPickingCommand(transfer_id, "picker", "operation-picking-start"))

    assert picking_list.lines[0].reserved_quantity == Decimal("4")
    assert picking_list.lines[0].lot_required is True
    assert dto.status == TransferStatus.PICKING.value
    assert events.events[0]["event_name"] == "TRANSFER_PICKING_STARTED"


def test_confirm_partial_picking_validates_barcode_lot_location_and_weight():
    repository = MemoryRepository()
    transfer_id = _reserved_transfer(repository)
    line_id = repository.get(transfer_id).lines[0].id
    StartTransferPickingUseCase(repository, _auth()).execute(
        StartTransferPickingCommand(transfer_id, "picker", "operation-picking-start"))
    validator = BarcodeValidator()
    events = EventSink()

    dto = ConfirmTransferPickingUseCase(repository, _auth(), validator, events).execute(
        ConfirmTransferPickingCommand(
            transfer_id,
            "picker",
            "operation-pick-partial",
            (TransferPickLineCommand(line_id, Decimal("2"), Decimal("590.225"), "barcode-1", "lot-1", "loc-1"),),
        ))

    assert dto.status == TransferStatus.PARTIALLY_PICKED.value
    assert repository.get(transfer_id).lines[0].picked_weight == Decimal("590.225")
    assert validator.scans == [("barcode-1", "lot-1", "loc-1")]
    assert events.events[0]["event_name"] == "TRANSFER_PICKED"
    assert events.events[0]["partial"] is True


def test_confirm_picking_requires_lot_and_rejects_duplicate_operation():
    repository = MemoryRepository()
    transfer_id = _reserved_transfer(repository)
    line_id = repository.get(transfer_id).lines[0].id
    StartTransferPickingUseCase(repository, _auth()).execute(
        StartTransferPickingCommand(transfer_id, "picker", "operation-picking-start"))

    with pytest.raises(ValueError):
        ConfirmTransferPickingUseCase(repository, _auth()).execute(
            ConfirmTransferPickingCommand(
                transfer_id,
                "picker",
                "operation-pick-missing-lot",
                (TransferPickLineCommand(line_id, Decimal("1"), Decimal("100"), "barcode-1", None, "loc-1"),),
            ))
    repository.operations.add("operation-pick-duplicate")
    with pytest.raises(DuplicateOperationError):
        ConfirmTransferPickingUseCase(repository, _auth()).execute(
            ConfirmTransferPickingCommand(
                transfer_id,
                "picker",
                "operation-pick-duplicate",
                (TransferPickLineCommand(line_id, Decimal("1"), Decimal("100"), "barcode-1", "lot-1", "loc-1"),),
            ))


def test_temperature_controlled_picking_requires_decimal_temperature_capture():
    repository = MemoryRepository()
    transfer_id = _reserved_transfer(repository)
    transfer = repository.get(transfer_id)
    line_id = transfer.lines[0].id
    transfer.lines[0].temperature_required = True
    StartTransferPickingUseCase(repository, _auth()).execute(
        StartTransferPickingCommand(transfer_id, "picker", "temperature-pick-start"))

    with pytest.raises(ValueError, match="temperature capture"):
        ConfirmTransferPickingUseCase(repository, _auth()).execute(
            ConfirmTransferPickingCommand(transfer_id, "picker", "temperature-missing", (
                TransferPickLineCommand(line_id, "4", "1180.450", "barcode", "lot", "location"),)))
    with pytest.raises(TypeError, match="Decimal"):
        ConfirmTransferPickingUseCase(repository, _auth()).execute(
            ConfirmTransferPickingCommand(transfer_id, "picker", "temperature-float", (
                TransferPickLineCommand(line_id, "4", "1180.450", "barcode", "lot", "location", 2.0),)))

    ConfirmTransferPickingUseCase(repository, _auth()).execute(
        ConfirmTransferPickingCommand(transfer_id, "picker", "temperature-valid", (
            TransferPickLineCommand(
                line_id, "4", "1180.450", "barcode", "lot", "location", Decimal("2.0")),)))
    assert transfer.lines[0].temperature_at_pick == Decimal("2.0")
