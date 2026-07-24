from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferReturnCommand,
    CreateTransferReturnCommand,
    DispatchTransferReturnCommand,
    ReceiveTransferReturnCommand,
    ReceiveTransferReturnLineCommand,
    TransferReturnLineCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.transfer_return_use_cases import (
    ApproveTransferReturnUseCase,
    CreateTransferReturnUseCase,
    DispatchTransferReturnUseCase,
    ReceiveTransferReturnUseCase,
)
from backend.domain.transfers.entities.stock_transfer import (
    StockTransfer, StockTransferLine, TransferReceipt, TransferReceiptLine,
)
from backend.domain.transfers.enums import (
    TransferNodeType, TransferReturnReason, TransferReturnStatus, TransferStatus, TransferType,
)
from backend.domain.transfers.exceptions import (
    DuplicateOperationError, SegregationOfDutiesError, TransferOverReceiptError,
)
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class Transfers:
    def __init__(self, transfer): self.transfer = transfer
    def get(self, transfer_id): return self.transfer if self.transfer.id == transfer_id else None
    def save(self, transfer): self.transfer = transfer


class Returns:
    def __init__(self): self.items, self.custody, self.operations = {}, [], set()
    def get(self, return_id): return self.items.get(return_id)
    def save(self, transfer_return, custody_event=None):
        self.items[transfer_return.id] = transfer_return
        if custody_event is not None: self.custody.append(custody_event)
    def operation_exists(self, operation_id): return operation_id in self.operations
    def record_operation(self, **values): self.operations.add(values["operation_id"])


class Permissions:
    def has_permission(self, user_id, permission_code):
        return (user_id, permission_code) in {
            ("receiver", TransferPermissions.RETURN_CREATE),
            ("manager", TransferPermissions.RETURN_APPROVE),
            ("return-dispatcher", TransferPermissions.RETURN_DISPATCH),
            ("origin-receiver", TransferPermissions.RECEIVE),
        }


class Inventory:
    def __init__(self): self.dispatches, self.receipts = [], []
    def dispatch_return(self, **values): self.dispatches.append(values)
    def receive_return(self, **values): self.receipts.append(values)


class Numbers:
    def next_return_number(self): return "RTN-2026-000001"


class Events:
    def __init__(self): self.items = []
    def collect(self, event): self.items.append(event)


def _received_transfer():
    line = StockTransferLine("product", "unit", Decimal("4"), Decimal("100"), pieces=Decimal("4"))
    transfer = StockTransfer(
        "TRF-RETURN", TransferType.BRANCH_TO_BRANCH,
        TransferNode(TransferNodeType.WAREHOUSE, "origin", "origin-wh", "origin-loc"),
        TransferNode(TransferNodeType.WAREHOUSE, "destination", "destination-wh", "destination-loc"),
        "requester", "create", [line],
    )
    transfer.submit(); transfer.approve("approver"); transfer.reserve(); transfer.start_picking()
    transfer.record_pick({line.id: ("4", "100")}); transfer.ready_to_dispatch()
    transfer.record_dispatch({line.id: "4"}, {line.id: "100"})
    transfer.receive(TransferReceipt(
        "shipment", "receiver", (TransferReceiptLine(line.id, "4", "100"),), "receive"))
    return transfer, line.id


def test_return_to_origin_has_approval_dispatch_transit_custody_and_receipt():
    transfer, line_id = _received_transfer()
    transfers, returns, inventory, events = Transfers(transfer), Returns(), Inventory(), Events()
    auth = TransferAuthorizationPolicy(Permissions())
    created = CreateTransferReturnUseCase(
        transfers, returns, auth, Numbers(), events).execute(CreateTransferReturnCommand(
            transfer.id, "receiver", "return-create", TransferReturnReason.QUALITY_REJECTION,
            (TransferReturnLineCommand(line_id, "4", "100", "4", "lot-1"),)))
    assert created.source_node == transfer.destination_node.identity()
    assert created.destination_node == transfer.origin_node.identity()
    assert created.status == TransferReturnStatus.REQUESTED.value

    approved = ApproveTransferReturnUseCase(transfers, returns, auth).execute(
        ApproveTransferReturnCommand(transfer.id, created.return_id, "manager", "return-approve"))
    assert approved.status == TransferReturnStatus.APPROVED.value
    assert transfer.status is TransferStatus.RETURN_IN_PROGRESS

    dispatched = DispatchTransferReturnUseCase(
        transfers, returns, inventory, auth, events).execute(DispatchTransferReturnCommand(
            transfer.id, created.return_id, "return-dispatcher", "carrier",
            "return-dispatch", "photo://dispatch", Decimal("2")))
    assert dispatched.status == TransferReturnStatus.IN_TRANSIT.value
    assert inventory.dispatches[0]["transfer_return"].id == created.return_id
    assert returns.custody[0].event_type == "RETURN_RELEASED"

    return_line_id = dispatched.lines[0].return_line_id
    completed = ReceiveTransferReturnUseCase(
        transfers, returns, inventory, auth, events).execute(ReceiveTransferReturnCommand(
            transfer.id, created.return_id, "origin-receiver", "carrier", "return-receive",
            (ReceiveTransferReturnLineCommand(return_line_id, "4", "100"),),
            "photo://receipt", Decimal("2.2")))
    assert completed.status == TransferReturnStatus.COMPLETED.value
    assert transfer.status is TransferStatus.CLOSED
    assert inventory.receipts[0]["transfer_return"].received_by_user_id == "origin-receiver"
    assert returns.custody[-1].event_type == "RETURN_ORIGIN_RECEIVED"
    assert [event["event_name"] for event in events.items] == [
        "TRANSFER_RETURN_CREATED", "TRANSFER_IN_TRANSIT", "TRANSFER_RETURN_COMPLETED"]


def test_return_rejects_excess_duplicate_operation_and_non_independent_approval():
    transfer, line_id = _received_transfer()
    transfers, returns = Transfers(transfer), Returns()
    auth = TransferAuthorizationPolicy(Permissions())
    with pytest.raises(TransferOverReceiptError):
        CreateTransferReturnUseCase(transfers, returns, auth, Numbers()).execute(
            CreateTransferReturnCommand(
                transfer.id, "receiver", "return-excess", TransferReturnReason.OVER_SHIPMENT,
                (TransferReturnLineCommand(line_id, "5", "100"),)))
    returns.operations.add("return-duplicate")
    with pytest.raises(DuplicateOperationError):
        CreateTransferReturnUseCase(transfers, returns, auth, Numbers()).execute(
            CreateTransferReturnCommand(
                transfer.id, "receiver", "return-duplicate", TransferReturnReason.DAMAGED,
                (TransferReturnLineCommand(line_id, "1", "25"),)))

    created = CreateTransferReturnUseCase(transfers, returns, auth, Numbers()).execute(
        CreateTransferReturnCommand(
            transfer.id, "receiver", "return-valid", TransferReturnReason.DAMAGED,
            (TransferReturnLineCommand(line_id, "1", "25"),)))
    with pytest.raises(SegregationOfDutiesError, match="independent"):
        returns.get(created.return_id).approve("receiver")
