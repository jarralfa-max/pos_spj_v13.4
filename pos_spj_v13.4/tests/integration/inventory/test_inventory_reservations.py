"""INV-10 — reservations + allocations: availability, lifecycle, idempotency, FEFO."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases import (
    AllocateReservationUseCase,
    CreateReservationUseCase,
    PostInventoryMovementUseCase,
    RegisterInventoryLotUseCase,
    ReleaseReservationUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    MovementType,
    ReservationSource,
    ReservationStatus,
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


def _receipt(conn, qty="10", loc="loc1", lot=None, op="r1", product="p1"):
    line = InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                        to_location_id=loc, lot_id=lot)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id="gr1",
        operation_id=op, created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")


def _available(conn, product="p1", loc="loc1", lot=None):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id=product, branch_id="b1", warehouse_id="w1",
                               inventory_status=InventoryStatus.AVAILABLE,
                               location_id=loc, lot_id=lot)
        return bal.available_quantity if bal else Decimal("0")


def _reserve(conn, qty="4", op="op-1", loc="loc1", lot=None):
    return CreateReservationUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1",
        source=ReservationSource.SALE, source_document_id="s1", quantity=Decimal(qty),
        operation_id=op, actor_user_id="u1", location_id=loc, lot_id=lot)


class TestCreateReservation:
    def test_reduces_availability_without_moving_stock(self, conn):
        _receipt(conn, "10")
        assert _available(conn) == Decimal("10")
        res = _reserve(conn, "4")
        assert res.success and _available(conn) == Decimal("6")
        with InventoryUnitOfWork(conn) as uow:
            bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                                   inventory_status=InventoryStatus.AVAILABLE,
                                   location_id="loc1")
            assert bal.quantity == Decimal("10")  # on-hand unchanged
            assert bal.reserved_quantity == Decimal("4")

    def test_over_availability_fails(self, conn):
        _receipt(conn, "3")
        res = _reserve(conn, "5")
        assert not res.success and res.error_code == "INVENTORY_RULE_VIOLATION"
        assert _available(conn) == Decimal("3")

    def test_no_balance_fails(self, conn):
        res = _reserve(conn, "1")
        assert not res.success and res.error_code == "INSUFFICIENT_AVAILABILITY"

    def test_idempotent(self, conn):
        _receipt(conn, "10")
        _reserve(conn, "4", op="op-1")
        res2 = _reserve(conn, "4", op="op-1")
        assert res2.data.get("already_processed") and _available(conn) == Decimal("6")

    def test_emits_reserved_event(self, conn):
        _receipt(conn, "10")
        _reserve(conn, "4")
        with InventoryUnitOfWork(conn) as uow:
            assert any(p["event_name"] == "INVENTORY_RESERVED"
                       for p in uow.outbox.list_pending())

    def test_permission_denied(self, conn):
        _receipt(conn, "10")
        class Deny:
            def has_permission(self, u, p):
                return False
        res = CreateReservationUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            source=ReservationSource.SALE, source_document_id="s1", quantity=Decimal("1"),
            operation_id="op-1", actor_user_id="u1", location_id="loc1")
        assert not res.success and res.error_code == "PERMISSION_DENIED"


class TestReleaseReservation:
    def test_release_restores_availability(self, conn):
        _receipt(conn, "10")
        r = _reserve(conn, "4")
        assert _available(conn) == Decimal("6")
        rel = ReleaseReservationUseCase().execute(
            conn, reservation_id=r.entity_id, operation_id="rel-1", actor_user_id="u1",
            reason="cancelada")
        assert rel.success and _available(conn) == Decimal("10")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.reservations.get(r.entity_id).status is ReservationStatus.RELEASED

    def test_release_idempotent(self, conn):
        _receipt(conn, "10")
        r = _reserve(conn, "4")
        ReleaseReservationUseCase().execute(conn, reservation_id=r.entity_id,
                                            operation_id="rel-1", actor_user_id="u1")
        res2 = ReleaseReservationUseCase().execute(conn, reservation_id=r.entity_id,
                                                   operation_id="rel-2", actor_user_id="u1")
        assert res2.data.get("already_processed") and _available(conn) == Decimal("10")

    def test_release_missing(self, conn):
        res = ReleaseReservationUseCase().execute(
            conn, reservation_id="nope", operation_id="rel-1", actor_user_id="u1")
        assert not res.success and res.error_code == "RESERVATION_NOT_FOUND"


class TestAllocateReservation:
    def test_allocates_lots_fefo(self, conn):
        # Aggregate availability at a lot-less location backs the reservation;
        # lot-specific balances feed the FEFO allocation (earliest expiry first).
        RegisterInventoryLotUseCase().execute(conn, product_id="p1", lot_code="SOON",
            origin_type=LotOrigin.PURCHASE, operation_id="l1", actor_user_id="u1",
            expiration_date="2026-07-25")
        RegisterInventoryLotUseCase().execute(conn, product_id="p1", lot_code="LATE",
            origin_type=LotOrigin.PURCHASE, operation_id="l2", actor_user_id="u1",
            expiration_date="2026-09-01")
        with InventoryUnitOfWork(conn) as uow:
            soon = uow.lots.get_by_code("p1", "SOON").id
            late = uow.lots.get_by_code("p1", "LATE").id
        _receipt(conn, "3", loc="stage", lot=None, op="r-agg")   # backs reservation
        _receipt(conn, "5", loc="loc1", lot=soon, op="r-soon")   # allocation candidate
        _receipt(conn, "5", loc="loc2", lot=late, op="r-late")   # allocation candidate
        r = _reserve(conn, "3", loc="stage", lot=None)
        alloc = AllocateReservationUseCase().execute(
            conn, reservation_id=r.entity_id, operation_id="al-1", actor_user_id="u1")
        assert alloc.success and alloc.data["allocations"] >= 1
        with InventoryUnitOfWork(conn) as uow:
            rows = uow.reservations.list_allocations(r.entity_id)
            assert rows and rows[0]["lot_id"] == soon  # FEFO → SOON first
            assert uow.reservations.get(r.entity_id).status is ReservationStatus.ALLOCATED
