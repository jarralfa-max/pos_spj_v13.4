"""INV-12 — transfer aggregate state machine + difference detection (domain)."""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities.transfer import (
    InventoryTransfer,
    InventoryTransferLine,
)
from backend.domain.inventory.enums import TransferDifferenceType, TransferStatus
from backend.domain.inventory.exceptions import InventoryDomainError


def _transfer(qty="10"):
    return InventoryTransfer.create(
        folio="TR-1", origin_branch_id="b1", origin_warehouse_id="w-orig",
        destination_branch_id="b2", destination_warehouse_id="w-dest",
        created_by_user_id="u1",
        lines=[InventoryTransferLine.create(product_id="p1", quantity=Decimal(qty))])


class TestTransferCreation:
    def test_same_warehouse_rejected(self):
        with pytest.raises(InventoryDomainError):
            InventoryTransfer.create(folio="X", origin_branch_id="b1",
                origin_warehouse_id="w", destination_branch_id="b1",
                destination_warehouse_id="w")

    def test_submit_requires_lines(self):
        t = InventoryTransfer.create(folio="X", origin_branch_id="b1",
            origin_warehouse_id="w1", destination_branch_id="b2",
            destination_warehouse_id="w2")
        with pytest.raises(InventoryDomainError):
            t.submit()


class TestLifecycle:
    def test_happy_path_to_received(self):
        t = _transfer("10")
        t.submit(); assert t.status is TransferStatus.PENDING_APPROVAL
        t.approve(user_id="mgr"); assert t.status is TransferStatus.APPROVED
        t.start_picking(); t.ready()
        t.dispatch(user_id="disp", carrier="DHL")
        assert t.status is TransferStatus.IN_TRANSIT
        assert t.lines[0].dispatched_quantity == Decimal("10")
        assert t.lines[0].in_transit_quantity == Decimal("10")
        t.receive(user_id="rec", received={t.lines[0].id: Decimal("10")})
        assert t.status is TransferStatus.RECEIVED
        assert t.lines[0].in_transit_quantity == Decimal("0")

    def test_invalid_transition(self):
        t = _transfer()
        with pytest.raises(InventoryDomainError):
            t.approve(user_id="mgr")  # cannot approve a DRAFT

    def test_receive_short_flags_difference(self):
        t = _transfer("10")
        t.submit(); t.approve(user_id="m"); t.start_picking(); t.ready()
        t.dispatch(user_id="d")
        t.receive(user_id="r", received={t.lines[0].id: Decimal("7")})
        assert t.status is TransferStatus.WITH_DIFFERENCES
        assert t.lines[0].difference_type is TransferDifferenceType.SHORT

    def test_receive_over_flags_difference(self):
        t = _transfer("10")
        t.submit(); t.approve(user_id="m"); t.start_picking(); t.ready()
        t.dispatch(user_id="d")
        t.receive(user_id="r", received={t.lines[0].id: Decimal("12")})
        assert t.status is TransferStatus.WITH_DIFFERENCES
        assert t.lines[0].difference_type is TransferDifferenceType.OVER

    def test_cancel_from_draft(self):
        t = _transfer()
        t.cancel()
        assert t.status is TransferStatus.CANCELLED
