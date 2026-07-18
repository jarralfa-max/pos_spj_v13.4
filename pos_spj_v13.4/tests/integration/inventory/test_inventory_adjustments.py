"""INV-14 — adjustments e2e: reason required, limit-gated approval, posting,
reverse, and the count → adjustment loop."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    ApproveAdjustmentUseCase,
    ApproveCountUseCase,
    ConfirmCountUseCase,
    CreateAdjustmentFromCountUseCase,
    CreateAdjustmentUseCase,
    CreateCountUseCase,
    PostAdjustmentUseCase,
    PostInventoryMovementUseCase,
    RecordCountUseCase,
    ReverseAdjustmentUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    AdjustmentReason,
    AdjustmentStatus,
    CountType,
    MovementType,
)
from backend.domain.inventory.value_objects.inventory_limit import InventoryOperationLimit
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


def _seed(conn, qty="10"):
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="loc1")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id="seed", created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _avail(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available


def _create(conn, delta, reason=AdjustmentReason.DAMAGE, op="adj-1"):
    return CreateAdjustmentUseCase().execute(
        conn, folio="ADJ-1", branch_id="b1", warehouse_id="w1", reason=reason,
        lines=[{"product_id": "p1", "quantity_delta": Decimal(str(delta)),
                "location_id": "loc1"}], operation_id=op, actor_user_id="clerk")


class TestCreateAndPost:
    def test_requires_reason(self, conn):
        # missing reason surfaces as a controlled rule violation, not a crash
        res = CreateAdjustmentUseCase().execute(
            conn, folio="X", branch_id="b1", warehouse_id="w1", reason=None,
            lines=[{"product_id": "p1", "quantity_delta": Decimal("1"),
                    "location_id": "loc1"}], operation_id="x", actor_user_id="c")
        assert not res.success and res.error_code == "INVENTORY_RULE_VIOLATION"

    def test_within_limit_posts_negative_delta(self, conn):
        _seed(conn, "10")
        r = _create(conn, "-3")  # no limit configured → WITHIN
        assert r.data["requires_approval"] is False
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        assert _avail(conn) == Decimal("7")

    def test_positive_delta_increases(self, conn):
        _seed(conn, "10")
        r = _create(conn, "5", reason=AdjustmentReason.SYSTEM_CORRECTION)
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        assert _avail(conn) == Decimal("15")

    def test_post_idempotent(self, conn):
        _seed(conn, "10")
        r = _create(conn, "-3")
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        assert _avail(conn) == Decimal("7")  # not 4


class TestLimitAndApproval:
    def _limit(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.limits.upsert_limit(scope_type="BRANCH", scope_id="b1",
                operation_kind="ADJUSTMENT",
                limit=InventoryOperationLimit(approval_threshold=Decimal("2")))

    def test_over_threshold_requires_approval_and_blocks_post(self, conn):
        _seed(conn, "10")
        self._limit(conn)
        r = _create(conn, "-5")  # magnitude 5 > approval 2
        assert r.data["requires_approval"] and r.data["status"] == "PENDING_APPROVAL"
        blocked = PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                                  operation_id="po-1", actor_user_id="clerk")
        assert not blocked.success and blocked.error_code == "APPROVAL_REQUIRED"
        assert _avail(conn) == Decimal("10")

    def test_creator_cannot_approve(self, conn):
        _seed(conn, "10")
        self._limit(conn)
        r = _create(conn, "-5")
        res = ApproveAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                                 operation_id="ap-1", actor_user_id="clerk")
        assert not res.success and res.error_code == "SEGREGATION_OF_DUTIES"

    def test_approved_then_posted(self, conn):
        _seed(conn, "10")
        self._limit(conn)
        r = _create(conn, "-5")
        ApproveAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                           operation_id="ap-1", actor_user_id="mgr")
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        assert _avail(conn) == Decimal("5")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.adjustments.get(r.entity_id).status is AdjustmentStatus.POSTED
            assert any(p["event_name"] == "INVENTORY_ADJUSTMENT_POSTED"
                       for p in uow.outbox.list_pending())


class TestReverse:
    def test_reverse_restores_balance(self, conn):
        _seed(conn, "10")
        r = _create(conn, "-3")
        PostAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                        operation_id="po-1", actor_user_id="clerk")
        assert _avail(conn) == Decimal("7")
        rev = ReverseAdjustmentUseCase().execute(conn, adjustment_id=r.entity_id,
                                                 operation_id="rv-1", actor_user_id="mgr",
                                                 reason="error")
        assert rev.success and _avail(conn) == Decimal("10")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.adjustments.get(r.entity_id).status is AdjustmentStatus.REVERSED


class TestCountToAdjustmentLoop:
    def test_approved_count_variance_becomes_adjustment(self, conn):
        _seed(conn, "10")
        cr = CreateCountUseCase().execute(
            conn, folio="CNT-1", count_type=CountType.CYCLE_COUNT, branch_id="b1",
            warehouse_id="w1", scope_lines=[{"product_id": "p1", "location_id": "loc1"}],
            operation_id="cc-1", actor_user_id="counter")
        line_id = cr.data["line_ids"][0]
        RecordCountUseCase().execute(conn, count_id=cr.entity_id, line_id=line_id,
                                     counted_quantity=Decimal("8"), operation_id="rc-1",
                                     actor_user_id="counter")
        ConfirmCountUseCase().execute(conn, count_id=cr.entity_id, operation_id="cf-1",
                                      actor_user_id="sup")
        ApproveCountUseCase().execute(conn, count_id=cr.entity_id, operation_id="ap-1",
                                      actor_user_id="mgr")
        adj = CreateAdjustmentFromCountUseCase().execute(
            conn, count_id=cr.entity_id, folio="ADJ-C1", operation_id="afc-1",
            actor_user_id="mgr")
        assert adj.success
        PostAdjustmentUseCase().execute(conn, adjustment_id=adj.entity_id,
                                        operation_id="po-1", actor_user_id="mgr")
        # count said 8, system had 10 → adjust down to 8
        assert _avail(conn) == Decimal("8")
