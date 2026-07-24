from decimal import Decimal

import pytest

from backend.domain.transfers.entities.stock_transfer import StockTransfer, StockTransferLine, TransferReceipt, TransferReceiptLine
from backend.domain.transfers.enums import TransferNodeType, TransferStatus, TransferType
from backend.domain.transfers.events import TransferEvents, event_payload
from backend.domain.transfers.exceptions import (TransferAlreadyReceivedError, TransferInvalidStatusError,
                                                 TransferOverReceiptError)
from backend.domain.transfers.policies.transfer_workflow_policy import TransferWorkflowPolicy
from backend.domain.transfers.value_objects.transfer_node import TransferNode


def _transfer() -> StockTransfer:
    return StockTransfer("TRF-2026-000001", TransferType.BRANCH_TO_BRANCH,
        TransferNode(TransferNodeType.WAREHOUSE, "branch-a", "warehouse-a"),
        TransferNode(TransferNodeType.WAREHOUSE, "branch-b", "warehouse-b"), "requester", "operation-create",
        [StockTransferLine("product", "unit", Decimal("4"), Decimal("1180.450"))])


def test_transfer_receipts_are_decimal_and_cumulative():
    transfer = _transfer(); line = transfer.lines[0]
    transfer.submit(); transfer.approve("approver"); transfer.reserve(); transfer.start_picking(); transfer.record_pick({line.id: (Decimal("4"), Decimal("1180.450"))}); transfer.ready_to_dispatch()
    transfer.record_dispatch({line.id: Decimal("4")}, {line.id: Decimal("1180.450")})
    first = TransferReceipt("shipment", "receiver", (TransferReceiptLine(line.id, Decimal("2"), Decimal("590.225")),), "receipt-one")
    assert transfer.receive(first) == []
    assert transfer.status is TransferStatus.PARTIALLY_RECEIVED
    second = TransferReceipt("shipment", "receiver", (TransferReceiptLine(line.id, Decimal("2"), Decimal("590.225")),), "receipt-two")
    transfer.receive(second)
    assert transfer.status is TransferStatus.RECEIVED
    assert line.received_quantity == Decimal("4")


def test_transfer_rejects_float_and_over_receipt():
    with pytest.raises(TypeError):
        StockTransferLine("product", "unit", 1.0)
    transfer = _transfer(); line = transfer.lines[0]
    transfer.submit(); transfer.approve("approver"); transfer.reserve(); transfer.start_picking(); transfer.record_pick({line.id: (Decimal("4"), Decimal("1180.450"))}); transfer.ready_to_dispatch()
    transfer.record_dispatch({line.id: Decimal("4")}, {line.id: Decimal("1180.450")})
    receipt = TransferReceipt("shipment", "receiver", (TransferReceiptLine(line.id, Decimal("5"), Decimal("1180.450")),), "receipt")
    with pytest.raises(TransferOverReceiptError): transfer.receive(receipt)


def test_partial_approval_picking_and_duplicate_receipt_are_protected():
    transfer = _transfer(); line = transfer.lines[0]
    transfer.submit(); transfer.approve("approver", {line.id: (Decimal("3"), Decimal("900"))})
    transfer.reserve({line.id: (Decimal("3"), Decimal("900"))}); transfer.start_picking()
    with pytest.raises(TransferInvalidStatusError):
        transfer.record_dispatch({line.id: Decimal("1")})
    transfer.record_pick({line.id: (Decimal("3"), Decimal("900"))}); transfer.ready_to_dispatch()
    transfer.record_dispatch({line.id: Decimal("3")}, {line.id: Decimal("900")})
    receipt = TransferReceipt("shipment", "receiver", (TransferReceiptLine(line.id, Decimal("3"), Decimal("900")),), "receipt")
    transfer.receive(receipt)
    with pytest.raises(TransferAlreadyReceivedError): transfer.receive(receipt)


def test_workflow_and_events_use_only_canonical_contracts():
    workflow = TransferWorkflowPolicy()
    assert workflow.can_transition(TransferStatus.IN_TRANSIT, TransferStatus.PARTIALLY_RECEIVED)
    assert not workflow.can_transition(TransferStatus.CANCELLED, TransferStatus.DRAFT)
    payload = event_payload(TransferEvents.DISPATCHED, operation_id="operation", entity_id="transfer", user_id="actor")
    assert payload["event_name"] == "TRANSFER_DISPATCHED"
    with pytest.raises(ValueError): event_payload("TRASPASO_INICIADO", operation_id="operation", entity_id="transfer", user_id="actor")
