from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    CreateTransferRequestCommand,
    ReserveTransferInventoryCommand,
    ReserveTransferLineCommand,
    SubmitTransferRequestCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_request_use_cases import (
    ApproveTransferRequestUseCase,
    CreateTransferRequestUseCase,
    SubmitTransferRequestUseCase,
)
from backend.application.transfers.use_cases.transfer_reservation_use_cases import ReserveTransferInventoryUseCase
from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.exceptions import DuplicateOperationError, TransferLotAllocationError
from backend.domain.transfers.policies.lot_allocation_policy import LotAllocationCandidate, TransferLotAllocation
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
        return "TRF-2026-000888"


class Permissions:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in {
            ("requester", TransferPermissions.REQUEST_CREATE),
            ("requester", TransferPermissions.REQUEST_SUBMIT),
            ("approver", TransferPermissions.APPROVE),
            ("warehouse", TransferPermissions.RESERVE),
        }


class InventoryGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[StockTransfer, str, str, tuple[TransferLotAllocation, ...]]] = []

    def reserve(self, *, transfer: StockTransfer, operation_id: str, actor_id: str,
                allocations: tuple[TransferLotAllocation, ...] = ()) -> None:
        self.calls.append((transfer, operation_id, actor_id, allocations))


class LotAvailability:
    def available_lots_for_transfer_line(self, *, transfer: StockTransfer,
                                         transfer_line_id: str) -> tuple[LotAllocationCandidate, ...]:
        product_id = transfer.lines[0].product_id
        return (
            LotAllocationCandidate(product_id, "lot-late", "loc-2", Decimal("2"), Decimal("600"), "2026-08-20"),
            LotAllocationCandidate(product_id, "lot-early", "loc-1", Decimal("2"), Decimal("600"), "2026-08-01"),
        )


class EventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def collect(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


def _node(branch: str, warehouse: str) -> TransferNode:
    return TransferNode(TransferNodeType.WAREHOUSE, branch, warehouse)


def _auth() -> TransferAuthorizationPolicy:
    return TransferAuthorizationPolicy(Permissions())


def _approved_transfer(repository: MemoryRepository) -> str:
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
    return created.transfer_id


def test_reserve_transfer_uses_inventory_gateway_and_fefo_lot_locations():
    repository = MemoryRepository()
    transfer_id = _approved_transfer(repository)
    line_id = repository.get(transfer_id).lines[0].id
    gateway = InventoryGateway()
    events = EventSink()

    dto = ReserveTransferInventoryUseCase(
        repository,
        gateway,
        _auth(),
        LotAvailability(),
        event_sink=events,
    ).execute(ReserveTransferInventoryCommand(
        transfer_id,
        "warehouse",
        "operation-reserve",
        (ReserveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
        allocate_lots_fefo=True,
    ))

    assert dto.status == TransferStatus.RESERVED.value
    assert repository.get(transfer_id).lines[0].reserved_weight == Decimal("1180.450")
    allocations = gateway.calls[0][3]
    assert [allocation.lot_id for allocation in allocations] == ["lot-early", "lot-late"]
    assert [allocation.location_id for allocation in allocations] == ["loc-1", "loc-2"]
    assert allocations[1].weight == Decimal("580.450")
    assert [event["event_name"] for event in events.events] == ["TRANSFER_RESERVED", "TRANSFER_ALLOCATED"]


def test_reserve_transfer_rejects_duplicate_operation_and_missing_lot_port():
    repository = MemoryRepository()
    transfer_id = _approved_transfer(repository)
    line_id = repository.get(transfer_id).lines[0].id
    repository.operations.add("operation-reserve")
    with pytest.raises(DuplicateOperationError):
        ReserveTransferInventoryUseCase(repository, InventoryGateway(), _auth()).execute(
            ReserveTransferInventoryCommand(transfer_id, "warehouse", "operation-reserve"))
    with pytest.raises(TransferLotAllocationError):
        ReserveTransferInventoryUseCase(repository, InventoryGateway(), _auth()).execute(
            ReserveTransferInventoryCommand(
                transfer_id,
                "warehouse",
                "operation-reserve-2",
                (ReserveTransferLineCommand(line_id, Decimal("4"), Decimal("1180.450")),),
                allocate_lots_fefo=True,
            ))
