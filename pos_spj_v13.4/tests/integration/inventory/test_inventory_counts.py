"""INV-13 — count flow e2e: expected snapshot, variance event, approval segregation."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases import (
    ApproveCountUseCase,
    ConfirmCountUseCase,
    CreateCountUseCase,
    PostInventoryMovementUseCase,
    RecordCountUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import CountStatus, CountType, MovementType
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


def _create(conn):
    return CreateCountUseCase().execute(
        conn, folio="CNT-1", count_type=CountType.BLIND_COUNT, branch_id="b1",
        warehouse_id="w1", scope_lines=[{"product_id": "p1", "location_id": "loc1"}],
        operation_id="cr-1", actor_user_id="counter")


class TestCountFlow:
    def test_snapshot_expected_from_balance(self, conn):
        _seed(conn, "10")
        r = _create(conn)
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            count = uow.counts.get(r.entity_id)
            assert count.lines[0].expected_quantity == Decimal("10")
            assert count.status is CountStatus.IN_PROGRESS and count.blind

    def test_matching_count_no_variance(self, conn):
        _seed(conn, "10")
        r = _create(conn)
        line_id = r.data["line_ids"][0]
        RecordCountUseCase().execute(conn, count_id=r.entity_id, line_id=line_id,
                                     counted_quantity=Decimal("10"), operation_id="rec-1",
                                     actor_user_id="counter")
        conf = ConfirmCountUseCase().execute(conn, count_id=r.entity_id,
                                             operation_id="cf-1", actor_user_id="sup")
        assert conf.data["has_variance"] is False
        assert conf.data["status"] == "COUNTED"

    def test_variance_emits_event_and_pending_approval(self, conn):
        _seed(conn, "10")
        r = _create(conn)
        line_id = r.data["line_ids"][0]
        RecordCountUseCase().execute(conn, count_id=r.entity_id, line_id=line_id,
                                     counted_quantity=Decimal("8"), operation_id="rec-1",
                                     actor_user_id="counter")
        conf = ConfirmCountUseCase().execute(conn, count_id=r.entity_id,
                                             operation_id="cf-1", actor_user_id="sup")
        assert conf.data["has_variance"] and conf.data["status"] == "PENDING_APPROVAL"
        with InventoryUnitOfWork(conn) as uow:
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert "INVENTORY_COUNT_VARIANCE_DETECTED" in events
            assert uow.counts.get(r.entity_id).lines[0].variance_quantity == Decimal("-2")

    def test_counter_cannot_approve_own_critical_variance(self, conn):
        _seed(conn, "10")
        r = _create(conn)
        line_id = r.data["line_ids"][0]
        RecordCountUseCase().execute(conn, count_id=r.entity_id, line_id=line_id,
                                     counted_quantity=Decimal("8"), operation_id="rec-1",
                                     actor_user_id="counter")
        ConfirmCountUseCase().execute(conn, count_id=r.entity_id, operation_id="cf-1",
                                      actor_user_id="sup")
        # counter approving their own variance → segregation
        res = ApproveCountUseCase().execute(conn, count_id=r.entity_id,
                                            operation_id="ap-1", actor_user_id="counter")
        assert not res.success and res.error_code == "SEGREGATION_OF_DUTIES"
        # a different approver succeeds
        ok = ApproveCountUseCase().execute(conn, count_id=r.entity_id, operation_id="ap-2",
                                           actor_user_id="mgr")
        assert ok.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.counts.get(r.entity_id).status is CountStatus.APPROVED

    def test_record_permission_denied(self, conn):
        _seed(conn, "10")
        r = _create(conn)
        class Deny:
            def has_permission(self, u, p):
                return False
        res = RecordCountUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, count_id=r.entity_id, line_id=r.data["line_ids"][0],
            counted_quantity=Decimal("9"), operation_id="rec-1", actor_user_id="x")
        assert not res.success and res.error_code == "PERMISSION_DENIED"
