"""INV-6 — ledger + balance use cases (post / reverse).

The single canonical write path: post a movement → project the balance
(negative-inventory guarded) → ledger + outbox atomic; reverse projects the exact
inverse. Idempotent by operation_id; balance is a reconstructable function of the
ledger.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    ReverseInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _receipt(op, qty="10", loc="loc1", product="p1"):
    line = InventoryMovementLine.create(
        product_id=product, quantity=Decimal(qty), to_location_id=loc)
    return InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GOODS_RECEIPT",
        source_document_id="gr1", operation_id=op, created_by_user_id="u1", lines=[line])


def _issue(op, qty="4", loc="loc1", product="p1"):
    line = InventoryMovementLine.create(
        product_id=product, quantity=Decimal(qty), from_location_id=loc)
    return InventoryMovement.create(
        movement_type=MovementType.SALE_ISSUE, branch_id="b1", warehouse_id="w1",
        source_module="sales", source_document_type="SALE", source_document_id="s1",
        operation_id=op, created_by_user_id="u1", lines=[line])


def _balance(conn, product="p1", status=InventoryStatus.AVAILABLE, loc="loc1"):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id=product, branch_id="b1", warehouse_id="w1",
                               inventory_status=status, location_id=loc)
        return bal.quantity if bal else Decimal("0")


class TestPostMovement:
    def test_receipt_increases_balance_and_emits_event(self, conn):
        res = PostInventoryMovementUseCase().execute(conn, _receipt("op-1"),
                                                     actor_user_id="u1")
        assert res.success
        assert _balance(conn) == Decimal("10")
        with InventoryUnitOfWork(conn) as uow:
            pending = uow.outbox.list_pending()
            assert any(p["event_name"] == "INVENTORY_MOVEMENT_POSTED" for p in pending)

    def test_idempotent_replay_does_not_double(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1"), actor_user_id="u1")
        res2 = PostInventoryMovementUseCase().execute(conn, _receipt("op-1"),
                                                      actor_user_id="u1")
        assert res2.success and res2.data.get("already_processed")
        assert _balance(conn) == Decimal("10")  # not 20

    def test_issue_within_stock_decreases(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1"), actor_user_id="u1")
        res = PostInventoryMovementUseCase().execute(conn, _issue("op-2", "4"),
                                                     actor_user_id="u1")
        assert res.success and _balance(conn) == Decimal("6")

    def test_issue_beyond_stock_blocked_by_default(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1", "3"), actor_user_id="u1")
        res = PostInventoryMovementUseCase().execute(conn, _issue("op-2", "5"),
                                                     actor_user_id="u1")
        assert not res.success and res.error_code == "INVENTORY_RULE_VIOLATION"
        assert _balance(conn) == Decimal("3")  # rolled back

    def test_negative_allowed_and_authorized_succeeds(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1", "3"), actor_user_id="u1")
        res = PostInventoryMovementUseCase().execute(
            conn, _issue("op-2", "5"), actor_user_id="u1",
            negative_allowed=True, authorized=True)
        assert res.success and _balance(conn) == Decimal("-2")

    def test_status_transfer_moves_between_buckets(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1", "10"), actor_user_id="u1")
        line = InventoryMovementLine.create(
            product_id="p1", quantity=Decimal("3"), from_location_id="loc1",
            to_location_id="loc1", from_status=InventoryStatus.AVAILABLE,
            to_status=InventoryStatus.QUARANTINED)
        mv = InventoryMovement.create(
            movement_type=MovementType.QUARANTINE_ENTRY, branch_id="b1", warehouse_id="w1",
            source_module="inventory", source_document_type="QUARANTINE",
            source_document_id="q1", operation_id="op-2", created_by_user_id="u1",
            lines=[line])
        res = PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        assert res.success
        assert _balance(conn, status=InventoryStatus.AVAILABLE) == Decimal("7")
        assert _balance(conn, status=InventoryStatus.QUARANTINED) == Decimal("3")

    def test_permission_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        res = PostInventoryMovementUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, _receipt("op-1"), actor_user_id="u1")
        assert not res.success and res.error_code == "PERMISSION_DENIED"
        assert _balance(conn) == Decimal("0")


class TestReverseMovement:
    def _post_receipt(self, conn, op="op-1"):
        PostInventoryMovementUseCase().execute(conn, _receipt(op, "10"), actor_user_id="u1")
        with InventoryUnitOfWork(conn) as uow:
            return uow.ledger.find_by_operation_id(op)["id"]

    def test_reverse_restores_balance(self, conn):
        mv_id = self._post_receipt(conn)
        assert _balance(conn) == Decimal("10")
        res = ReverseInventoryMovementUseCase().execute(
            conn, movement_id=mv_id, operation_id="rev-1", actor_user_id="u1",
            reason="error de captura")
        assert res.success and _balance(conn) == Decimal("0")

    def test_reverse_marks_original_and_blocks_second(self, conn):
        mv_id = self._post_receipt(conn)
        ReverseInventoryMovementUseCase().execute(
            conn, movement_id=mv_id, operation_id="rev-1", actor_user_id="u1", reason="x")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.ledger.get(mv_id)["status"] == "REVERSED"
        res2 = ReverseInventoryMovementUseCase().execute(
            conn, movement_id=mv_id, operation_id="rev-2", actor_user_id="u1", reason="y")
        assert not res2.success and res2.error_code == "ALREADY_REVERSED"

    def test_reverse_is_idempotent_on_operation_id(self, conn):
        mv_id = self._post_receipt(conn)
        ReverseInventoryMovementUseCase().execute(
            conn, movement_id=mv_id, operation_id="rev-1", actor_user_id="u1", reason="x")
        res = ReverseInventoryMovementUseCase().execute(
            conn, movement_id=mv_id, operation_id="rev-1", actor_user_id="u1", reason="x")
        assert res.success and res.data.get("already_processed")
        assert _balance(conn) == Decimal("0")  # not double-reversed

    def test_reverse_missing_movement(self, conn):
        res = ReverseInventoryMovementUseCase().execute(
            conn, movement_id=new_uuid(), operation_id="rev-1", actor_user_id="u1",
            reason="x")
        assert not res.success and res.error_code == "MOVEMENT_NOT_FOUND"


class TestBalanceReconstructable:
    def test_receipt_issue_reverse_nets_out(self, conn):
        PostInventoryMovementUseCase().execute(conn, _receipt("op-1", "10"), actor_user_id="u1")
        PostInventoryMovementUseCase().execute(conn, _issue("op-2", "4"), actor_user_id="u1")
        assert _balance(conn) == Decimal("6")
        with InventoryUnitOfWork(conn) as uow:
            issue_id = uow.ledger.find_by_operation_id("op-2")["id"]
        ReverseInventoryMovementUseCase().execute(
            conn, movement_id=issue_id, operation_id="rev-1", actor_user_id="u1", reason="x")
        assert _balance(conn) == Decimal("10")  # issue undone
