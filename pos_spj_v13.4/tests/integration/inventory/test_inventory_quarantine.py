"""INV-15 — quarantine e2e: AVAILABLE↔QUARANTINED, segregation, disposal."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    DisposeQuarantineUseCase,
    PostInventoryMovementUseCase,
    QuarantineStockUseCase,
    ReleaseQuarantineUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementType,
    QuarantineReason,
    QuarantineStatus,
)
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


def _bucket(conn, status):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                               inventory_status=status, location_id="loc1")
        return bal.quantity if bal else Decimal("0")


def _available(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available


def _quarantine(conn, qty="4", op="q-1", user="qa"):
    return QuarantineStockUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal(qty), operation_id=op,
        actor_user_id=user, location_id="loc1")


class TestQuarantineFlow:
    def test_quarantine_moves_available_to_quarantined(self, conn):
        _seed(conn, "10")
        r = _quarantine(conn, "4")
        assert r.success
        assert _available(conn) == Decimal("6")
        assert _bucket(conn, InventoryStatus.AVAILABLE) == Decimal("6")
        assert _bucket(conn, InventoryStatus.QUARANTINED) == Decimal("4")
        with InventoryUnitOfWork(conn) as uow:
            assert any(p["event_name"] == "INVENTORY_QUARANTINED"
                       for p in uow.outbox.list_pending())

    def test_quarantine_beyond_available_blocked(self, conn):
        _seed(conn, "3")
        r = _quarantine(conn, "5")
        assert not r.success and r.error_code == "INVENTORY_RULE_VIOLATION"
        assert _available(conn) == Decimal("3")

    def test_release_returns_to_available_by_distinct_user(self, conn):
        _seed(conn, "10")
        r = _quarantine(conn, "4", user="qa")
        rel = ReleaseQuarantineUseCase().execute(
            conn, quarantine_id=r.entity_id, operation_id="rel-1", actor_user_id="mgr")
        assert rel.success
        assert _available(conn) == Decimal("10")
        assert _bucket(conn, InventoryStatus.QUARANTINED) == Decimal("0")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.quarantines.get(r.entity_id).status is QuarantineStatus.RELEASED

    def test_blocker_cannot_self_release(self, conn):
        _seed(conn, "10")
        r = _quarantine(conn, "4", user="qa")
        rel = ReleaseQuarantineUseCase().execute(
            conn, quarantine_id=r.entity_id, operation_id="rel-1", actor_user_id="qa")
        assert not rel.success and rel.error_code == "SEGREGATION_OF_DUTIES"
        assert _available(conn) == Decimal("6")  # unchanged

    def test_dispose_issues_out_of_quarantine(self, conn):
        _seed(conn, "10")
        r = _quarantine(conn, "4", user="qa")
        disp = DisposeQuarantineUseCase().execute(
            conn, quarantine_id=r.entity_id, operation_id="dsp-1", actor_user_id="mgr",
            reason="microbiológico")
        assert disp.success
        assert _bucket(conn, InventoryStatus.QUARANTINED) == Decimal("0")
        assert _available(conn) == Decimal("6")  # available never got it back
        with InventoryUnitOfWork(conn) as uow:
            assert uow.quarantines.get(r.entity_id).status is QuarantineStatus.DISPOSED

    def test_quarantine_permission_denied(self, conn):
        _seed(conn, "10")
        class Deny:
            def has_permission(self, u, p):
                return False
        r = QuarantineStockUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reason=QuarantineReason.QUALITY_FAILURE, quantity=Decimal("4"),
            operation_id="q-1", actor_user_id="qa", location_id="loc1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
