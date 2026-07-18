"""INV-12 — transfer flow e2e: §24 stock rule, differences, segregation, idempotency."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    ApproveTransferUseCase,
    CreateTransferUseCase,
    DispatchTransferUseCase,
    PostInventoryMovementUseCase,
    ReceiveTransferUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType, TransferStatus
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _seed_origin(conn, qty="10"):
    """Stock at origin warehouse (location = warehouse for transfer movements)."""
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="w-orig")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w-orig",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="seed", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _avail(conn, branch):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id=branch).available


def _create_approved(conn, qty="10"):
    r = CreateTransferUseCase().execute(
        conn, folio="TR-1", origin_branch_id="b1", origin_warehouse_id="w-orig",
        destination_branch_id="b2", destination_warehouse_id="w-dest",
        lines=[{"product_id": "p1", "quantity": Decimal(qty)}], operation_id="cr-1",
        actor_user_id="u1")
    ApproveTransferUseCase().execute(conn, transfer_id=r.entity_id, operation_id="ap-1",
                                     actor_user_id="mgr")
    return r.entity_id


class TestTransferStockRule:
    def test_dispatch_decreases_origin_only(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        assert _avail(conn, "b1") == Decimal("10") and _avail(conn, "b2") == Decimal("0")
        DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                          actor_user_id="disp", carrier="DHL")
        # §24: origin drops, destination does NOT gain until received
        assert _avail(conn, "b1") == Decimal("0")
        assert _avail(conn, "b2") == Decimal("0")

    def test_receive_increases_destination(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                          actor_user_id="disp")
        with InventoryUnitOfWork(conn) as uow:
            line_id = uow.transfers.get(tid).lines[0].id
        res = ReceiveTransferUseCase().execute(
            conn, transfer_id=tid, received={line_id: Decimal("10")}, operation_id="rc-1",
            actor_user_id="recv")
        assert res.data["status"] == "RECEIVED"
        assert _avail(conn, "b2") == Decimal("10")

    def test_short_receipt_flags_differences(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                          actor_user_id="disp")
        with InventoryUnitOfWork(conn) as uow:
            line_id = uow.transfers.get(tid).lines[0].id
        res = ReceiveTransferUseCase().execute(
            conn, transfer_id=tid, received={line_id: Decimal("7")}, operation_id="rc-1",
            actor_user_id="recv")
        assert res.data["status"] == "WITH_DIFFERENCES"
        assert _avail(conn, "b2") == Decimal("7")
        with InventoryUnitOfWork(conn) as uow:
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert "INVENTORY_TRANSFER_DIFFERENCE_DETECTED" in events


class TestSegregationAndIdempotency:
    def test_dispatcher_cannot_receive(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                          actor_user_id="same")
        with InventoryUnitOfWork(conn) as uow:
            line_id = uow.transfers.get(tid).lines[0].id
        res = ReceiveTransferUseCase().execute(
            conn, transfer_id=tid, received={line_id: Decimal("10")}, operation_id="rc-1",
            actor_user_id="same")  # dispatcher == receiver
        assert not res.success and res.error_code == "SEGREGATION_OF_DUTIES"

    def test_dispatch_idempotent(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                          actor_user_id="disp")
        res2 = DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-2",
                                                 actor_user_id="disp")
        assert res2.data.get("already_processed")
        assert _avail(conn, "b1") == Decimal("0")  # not decremented twice

    def test_dispatch_permission_denied(self, conn):
        _seed_origin(conn, "10")
        tid = _create_approved(conn, "10")
        class Deny:
            def has_permission(self, u, p):
                return False
        res = DispatchTransferUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, transfer_id=tid, operation_id="dp-1", actor_user_id="disp")
        assert not res.success and res.error_code == "PERMISSION_DENIED"
        assert _avail(conn, "b1") == Decimal("10")

    def test_insufficient_origin_stock_rolls_back(self, conn):
        _seed_origin(conn, "3")
        tid = _create_approved(conn, "10")
        res = DispatchTransferUseCase().execute(conn, transfer_id=tid, operation_id="dp-1",
                                                actor_user_id="disp")
        assert not res.success and res.error_code == "INVENTORY_RULE_VIOLATION"
        # transfer state unchanged (still APPROVED), origin intact
        assert _avail(conn, "b1") == Decimal("3")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.transfers.get(tid).status is TransferStatus.APPROVED
