from decimal import Decimal

import pytest

from backend.application.transfers.authorization import TransferAuthorizationPolicy
from backend.application.transfers.commands.transfer_request_commands import (
    CaptureBlindReceiptCommand,
    ConfirmBlindReceiptCommand,
    ReceiveTransferLineCommand,
    StartBlindReceiptCommand,
)
from backend.application.transfers.permissions import TransferPermissions
from backend.application.transfers.use_cases.blind_receipt_use_cases import (
    CaptureBlindReceiptUseCase,
    ConfirmBlindReceiptUseCase,
    StartBlindReceiptUseCase,
)
from backend.application.transfers.use_cases.transfer_receipt_use_cases import ConfirmTransferReceiptUseCase
from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine
from backend.domain.transfers.entities.transfer_shipment import TransferShipment, TransferShipmentLine
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.exceptions import PermissionDeniedError, TransferInvalidStatusError
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class Transfers:
    def __init__(self, transfer): self.transfer = transfer
    def get(self, transfer_id): return self.transfer if transfer_id == self.transfer.id else None
    def save(self, transfer): self.transfer = transfer


class Shipments:
    def __init__(self, transfer_id, line_id):
        self.shipment = TransferShipment(
            transfer_id, "SHP-BLIND", "dispatcher", "verifier",
            (TransferShipmentLine(line_id, Decimal("4"), Decimal("100")),), id="shipment",
        )
    def get(self, shipment_id): return self.shipment if shipment_id == "shipment" else None


class Counts:
    def __init__(self): self.saved, self.operations = {}, set()
    def get(self, count_id): return self.saved.get(count_id)
    def save(self, count): self.saved[count.id] = count
    def operation_exists(self, operation_id): return operation_id in self.operations
    def record_operation(self, **values): self.operations.add(values["operation_id"])


class Receipts:
    def __init__(self): self.saved, self.operations = {}, set()
    def save(self, receipt, differences): self.saved[receipt.id] = receipt
    def operation_exists(self, operation_id): return operation_id in self.operations
    def received_totals(self, shipment_id):
        totals = {}
        for receipt in self.saved.values():
            if receipt.shipment_id == shipment_id:
                for line in receipt.lines:
                    quantity, weight = totals.get(line.transfer_line_id, (Decimal("0"), Decimal("0")))
                    totals[line.transfer_line_id] = (quantity + line.observed_quantity,
                                                     weight + line.observed_weight)
        return totals
    def record_operation(self, **values): self.operations.add(values["operation_id"])


class Permissions:
    def has_permission(self, user_id, permission_code):
        return user_id == "receiver" and permission_code in {
            TransferPermissions.BLIND_RECEIVE,
            TransferPermissions.RECEIVE,
            TransferPermissions.PARTIAL_RECEIVE,
        }


class Inventory:
    def __init__(self): self.received = []
    def receive(self, **values): self.received.append(values)


def _fixture(blind=True):
    line = StockTransferLine("product", "unit", Decimal("4"), Decimal("100"))
    transfer = StockTransfer(
        "TRF-BLIND", TransferType.BRANCH_TO_BRANCH,
        TransferNode(TransferNodeType.WAREHOUSE, "origin", "origin-wh"),
        TransferNode(TransferNodeType.WAREHOUSE, "destination", "destination-wh"),
        "requester", "create", [line], blind_receipt_required=blind,
    )
    transfer.submit(); transfer.approve("approver"); transfer.reserve(); transfer.start_picking()
    transfer.record_pick({line.id: (Decimal("4"), Decimal("100"))})
    transfer.ready_to_dispatch(); transfer.record_dispatch({line.id: Decimal("4")}, {line.id: Decimal("100")})
    transfers, shipments, counts, receipts, inventory = (
        Transfers(transfer), Shipments(transfer.id, line.id), Counts(), Receipts(), Inventory())
    authorization = TransferAuthorizationPolicy(Permissions())
    receipt_use_case = ConfirmTransferReceiptUseCase(
        transfers, shipments, receipts, inventory, authorization)
    return transfer, line.id, transfers, shipments, counts, receipts, authorization, receipt_use_case


def test_blind_count_hides_expected_during_capture_then_reveals_after_confirmation():
    transfer, line_id, transfers, shipments, counts, receipts, auth, receipt_use_case = _fixture()
    started = StartBlindReceiptUseCase(transfers, shipments, counts, auth).execute(
        StartBlindReceiptCommand(transfer.id, "shipment", "receiver", "blind-start"))
    assert started.status == "CAPTURING"
    assert not hasattr(started, "expected_quantity")

    captured = CaptureBlindReceiptUseCase(transfers, counts, auth).execute(
        CaptureBlindReceiptCommand(started.count_id, "receiver", "blind-capture", (
            ReceiveTransferLineCommand(line_id, Decimal("3"), Decimal("98")),)))
    assert captured.lines[0].observed_quantity == Decimal("3")
    assert all("expected" not in field for field in captured.__dataclass_fields__)
    recaptured = CaptureBlindReceiptUseCase(transfers, counts, auth).execute(
        CaptureBlindReceiptCommand(started.count_id, "receiver", "blind-recapture", (
            ReceiveTransferLineCommand(line_id, Decimal("3.5"), Decimal("99")),)))
    assert recaptured.lines[0].observed_quantity == Decimal("3.5")

    confirmed = ConfirmBlindReceiptUseCase(
        transfers, shipments, receipts, counts, auth, receipt_use_case).execute(
            ConfirmBlindReceiptCommand(started.count_id, "receiver", "blind-confirm"))
    comparison = confirmed.comparisons[0]
    assert confirmed.status == "CONFIRMED"
    assert comparison.expected_quantity == Decimal("4")
    assert comparison.quantity_difference == Decimal("-0.5")
    assert comparison.expected_weight == Decimal("100")
    assert comparison.weight_difference == Decimal("-1")

    with pytest.raises(TransferInvalidStatusError, match="cannot be edited"):
        CaptureBlindReceiptUseCase(transfers, counts, auth).execute(
            CaptureBlindReceiptCommand(started.count_id, "receiver", "blind-edit-after-confirm", (
                ReceiveTransferLineCommand(line_id, Decimal("4"), Decimal("100")),)))


def test_blind_receipt_must_be_configured_and_assigned_receiver_is_enforced():
    transfer, _line_id, transfers, shipments, counts, _receipts, auth, _receipt = _fixture(False)
    with pytest.raises(PermissionDeniedError, match="not enabled"):
        StartBlindReceiptUseCase(transfers, shipments, counts, auth).execute(
            StartBlindReceiptCommand(transfer.id, "shipment", "receiver", "blind-disabled"))

    transfer.blind_receipt_required = True
    started = StartBlindReceiptUseCase(transfers, shipments, counts, auth).execute(
        StartBlindReceiptCommand(transfer.id, "shipment", "receiver", "blind-enabled"))
    with pytest.raises(PermissionDeniedError, match="assigned receiver"):
        CaptureBlindReceiptUseCase(transfers, counts, auth).execute(
            CaptureBlindReceiptCommand(started.count_id, "other-user", "blind-wrong-user", (
                ReceiveTransferLineCommand("line", Decimal("1")),)))
