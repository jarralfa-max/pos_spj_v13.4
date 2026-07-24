from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    CreateTransferRequestCommand,
    EditTransferRequestCommand,
    RejectTransferRequestCommand,
    SubmitTransferRequestCommand,
    TransferApprovalLineCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_request_use_cases import (
    ApproveTransferRequestUseCase,
    CreateTransferRequestUseCase,
    EditTransferRequestUseCase,
    RejectTransferRequestUseCase,
    SubmitTransferRequestUseCase,
)
from backend.domain.transfers.entities.stock_transfer import StockTransfer
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.exceptions import (DuplicateOperationError, SegregationOfDutiesError,
                                                 TransferInvalidStatusError)
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
        assert operation_type.startswith("TRANSFER_REQUEST_")
        self.operations.add(operation_id)


class NumberGenerator:
    def next_transfer_number(self) -> str:
        return "TRF-2026-000777"


class EventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def collect(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


class Permissions:
    def __init__(self, permissions: set[tuple[str, str]]) -> None:
        self.permissions = permissions

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return (user_id, permission_code) in self.permissions


def _node(branch: str, warehouse: str) -> TransferNode:
    return TransferNode(TransferNodeType.WAREHOUSE, branch, warehouse)


def _line(quantity: str = "4", weight: str = "1180.450") -> TransferRequestLineCommand:
    return TransferRequestLineCommand("product", "unit", Decimal(quantity), Decimal(weight), pieces=Decimal(quantity))


def _auth() -> TransferAuthorizationPolicy:
    return TransferAuthorizationPolicy()


def _created_pending(repository: MemoryRepository) -> str:
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand("requester", "operation-create", TransferType.BRANCH_TO_BRANCH,
                                     _node("branch-a", "warehouse-a"), _node("branch-b", "warehouse-b"), (_line(),)))
    SubmitTransferRequestUseCase(repository, _auth()).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))
    return created.transfer_id


def test_create_transfer_request_uses_permissions_priority_and_canonical_event():
    repository = MemoryRepository()
    events = EventSink()
    use_case = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator(), events)

    dto = use_case.execute(CreateTransferRequestCommand(
        requested_by_user_id="requester",
        operation_id="operation-create",
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=_node("branch-a", "warehouse-a"),
        destination_node=_node("branch-b", "warehouse-b"),
        lines=(_line(),),
        priority="URGENT",
    ))

    assert dto.transfer_number == "TRF-2026-000777"
    assert dto.status == TransferStatus.DRAFT.value
    assert dto.priority == "URGENT"
    assert dto.lines[0].requested_weight == Decimal("1180.450")
    assert events.events[0]["event_name"] == "TRANSFER_REQUEST_CREATED"


def test_create_transfer_request_rejects_duplicate_operation():
    repository = MemoryRepository()
    repository.operations.add("operation-create")
    use_case = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator())
    command = CreateTransferRequestCommand("requester", "operation-create", TransferType.BRANCH_TO_BRANCH,
                                           _node("branch-a", "warehouse-a"), _node("branch-b", "warehouse-b"), (_line(),))

    with pytest.raises(DuplicateOperationError):
        use_case.execute(command)


def test_edit_transfer_request_only_allows_draft_priority_and_decimal_lines():
    repository = MemoryRepository()
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand("requester", "operation-create", TransferType.BRANCH_TO_BRANCH,
                                     _node("branch-a", "warehouse-a"), _node("branch-b", "warehouse-b"), (_line(),)))
    dto = EditTransferRequestUseCase(repository, _auth()).execute(
        EditTransferRequestCommand(created.transfer_id, "requester", "operation-edit", (_line("2", "590.225"),), "HIGH"))

    assert dto.priority == "HIGH"
    assert dto.lines[0].requested_quantity == Decimal("2")
    assert "operation-edit" in repository.operations

    transfer = repository.get(created.transfer_id)
    assert transfer is not None
    transfer.submit()
    with pytest.raises(TransferInvalidStatusError):
        EditTransferRequestUseCase(repository, _auth()).execute(
            EditTransferRequestCommand(created.transfer_id, "requester", "operation-edit-2", (_line("1"),), "LOW"))


def test_submit_transfer_request_requires_backend_permission_and_emits_event():
    repository = MemoryRepository()
    events = EventSink()
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand("requester", "operation-create", TransferType.BRANCH_TO_BRANCH,
                                     _node("branch-a", "warehouse-a"), _node("branch-b", "warehouse-b"), (_line(),)))

    dto = SubmitTransferRequestUseCase(repository, _auth(), events).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))

    assert dto.status == TransferStatus.PENDING_APPROVAL.value
    assert events.events[0]["event_name"] == "TRANSFER_REQUEST_SUBMITTED"
    assert TransferPermissions.REQUEST_SUBMIT == "TRANSFERS_REQUEST_SUBMIT"


def test_approve_transfer_request_supports_full_approval_workflow_and_event():
    repository = MemoryRepository()
    events = EventSink()
    transfer_id = _created_pending(repository)

    dto = ApproveTransferRequestUseCase(repository, _auth(), event_sink=events).execute(
        ApproveTransferRequestCommand(transfer_id, "approver", "operation-approve"))

    transfer = repository.get(transfer_id)
    assert transfer is not None
    assert dto.status == TransferStatus.APPROVED.value
    assert transfer.approved_by_user_id == "approver"
    assert transfer.lines[0].approved_quantity == Decimal("4")
    assert events.events[0]["event_name"] == "TRANSFER_APPROVED"
    assert events.events[0]["partial"] is False


def test_partial_approval_requires_partial_permission_and_changes_line_values():
    repository = MemoryRepository()
    transfer_id = _created_pending(repository)
    transfer = repository.get(transfer_id)
    assert transfer is not None
    line_id = transfer.lines[0].id
    auth = TransferAuthorizationPolicy(Permissions({("approver", TransferPermissions.PARTIAL_APPROVE)}))

    dto = ApproveTransferRequestUseCase(repository, auth).execute(
        ApproveTransferRequestCommand(
            transfer_id,
            "approver",
            "operation-partial-approve",
            (TransferApprovalLineCommand(line_id, Decimal("2"), Decimal("590.225")),),
            "Destino solo requiere media carga",
        ))

    assert dto.status == TransferStatus.APPROVED.value
    assert repository.get(transfer_id).lines[0].approved_quantity == Decimal("2")


def test_reject_transfer_request_uses_reject_permission_and_canonical_event():
    repository = MemoryRepository()
    events = EventSink()
    transfer_id = _created_pending(repository)
    auth = TransferAuthorizationPolicy(Permissions({("approver", TransferPermissions.REJECT)}))

    dto = RejectTransferRequestUseCase(repository, auth, events).execute(
        RejectTransferRequestCommand(transfer_id, "approver", "operation-reject", "No autorizado"))

    assert dto.status == TransferStatus.REJECTED.value
    assert events.events[0]["event_name"] == "TRANSFER_REJECTED"
    assert events.events[0]["reason"] == "No autorizado"


def test_elevated_transfer_request_cannot_be_self_approved():
    repository = MemoryRepository()
    created = CreateTransferRequestUseCase(repository, _auth(), NumberGenerator()).execute(
        CreateTransferRequestCommand("requester", "operation-create", TransferType.BRANCH_TO_BRANCH,
                                     _node("branch-a", "warehouse-a"), _node("branch-b", "warehouse-b"),
                                     (_line(),), priority="EMERGENCY"))
    SubmitTransferRequestUseCase(repository, _auth()).execute(
        SubmitTransferRequestCommand(created.transfer_id, "requester", "operation-submit"))

    with pytest.raises(SegregationOfDutiesError):
        ApproveTransferRequestUseCase(repository, _auth()).execute(
            ApproveTransferRequestCommand(created.transfer_id, "requester", "operation-self-approve"))
