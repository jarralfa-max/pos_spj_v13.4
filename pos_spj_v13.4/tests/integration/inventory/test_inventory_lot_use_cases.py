"""INV-7 — lot persistence + use cases (register, quality block/release) + FEFO
allocation over the repository."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases import (
    RegisterInventoryLotUseCase,
    SetLotQualityStatusUseCase,
)
from backend.domain.inventory.enums import (
    AllocationStrategy,
    LotOrigin,
    LotQualityStatus,
)
from backend.domain.inventory.services import LotAllocationService, LotCandidate
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


class TestLotSchema:
    def test_inventory_lots_born_clean(self, conn):
        cols = {r[1]: (r[2] or "").upper()
                for r in conn.execute("PRAGMA table_info(inventory_lots)").fetchall()}
        pk = [r for r in conn.execute("PRAGMA table_info(inventory_lots)").fetchall() if r[5]]
        assert pk and "INT" not in (pk[0][2] or "").upper()  # TEXT UUIDv7 id


class TestRegisterLot:
    def test_register_and_idempotency(self, conn):
        uc = RegisterInventoryLotUseCase()
        r1 = uc.execute(conn, product_id="p1", lot_code="L-1",
                        origin_type=LotOrigin.PURCHASE, operation_id="op-1",
                        actor_user_id="u1", expiration_date="2026-08-01")
        assert r1.success
        r2 = uc.execute(conn, product_id="p1", lot_code="L-1",
                        origin_type=LotOrigin.PURCHASE, operation_id="op-2",
                        actor_user_id="u1")
        assert r2.success and r2.data.get("already_processed")
        assert r2.entity_id == r1.entity_id
        with InventoryUnitOfWork(conn) as uow:
            assert any(p["event_name"] == "INVENTORY_LOT_CREATED"
                       for p in uow.outbox.list_pending())

    def test_permission_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        r = RegisterInventoryLotUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
            operation_id="op-1", actor_user_id="u1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"


class TestQualityStatus:
    def _lot(self, conn):
        RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
            operation_id="op-1", actor_user_id="u1")
        with InventoryUnitOfWork(conn) as uow:
            return uow.lots.get_by_code("p1", "L-1").id

    def test_block_then_release(self, conn):
        lot_id = self._lot(conn)
        rb = SetLotQualityStatusUseCase().execute(
            conn, lot_id=lot_id, new_status=LotQualityStatus.BLOCKED,
            operation_id="op-b", actor_user_id="qa", reason="temperatura")
        assert rb.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.BLOCKED
        rr = SetLotQualityStatusUseCase().execute(
            conn, lot_id=lot_id, new_status=LotQualityStatus.RELEASED,
            operation_id="op-r", actor_user_id="qa")
        assert rr.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).is_released
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert "INVENTORY_LOT_BLOCKED" in events and "INVENTORY_LOT_RELEASED" in events

    def test_release_requires_release_permission(self, conn):
        lot_id = self._lot(conn)

        class OnlyBlock:
            def has_permission(self, u, p):
                return p != "INVENTORY_LOT_RELEASE"
        r = SetLotQualityStatusUseCase(InventoryAuthorizationPolicy(OnlyBlock())).execute(
            conn, lot_id=lot_id, new_status=LotQualityStatus.RELEASED,
            operation_id="op-r", actor_user_id="u1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_missing_lot(self, conn):
        r = SetLotQualityStatusUseCase().execute(
            conn, lot_id="nope", new_status=LotQualityStatus.BLOCKED,
            operation_id="op-x", actor_user_id="u1")
        assert not r.success and r.error_code == "LOT_NOT_FOUND"


class TestFefoOverRepository:
    def test_candidates_feed_fefo(self, conn):
        uc = RegisterInventoryLotUseCase()
        uc.execute(conn, product_id="p1", lot_code="LATE", origin_type=LotOrigin.PURCHASE,
                   operation_id="o1", actor_user_id="u1", expiration_date="2026-09-01")
        uc.execute(conn, product_id="p1", lot_code="SOON", origin_type=LotOrigin.PURCHASE,
                   operation_id="o2", actor_user_id="u1", expiration_date="2026-07-25")
        with InventoryUnitOfWork(conn) as uow:
            rows = uow.lots.list_for_product("p1")
        candidates = [
            LotCandidate(lot_id=r["id"], available_quantity=Decimal("10"),
                         expiration_date=r["expiration_date"],
                         quality_status=LotQualityStatus(r["quality_status"]))
            for r in rows]
        plan = LotAllocationService().allocate(
            candidates, Decimal("5"), strategy=AllocationStrategy.FEFO)
        soon_id = next(r["id"] for r in rows if r["lot_code"] == "SOON")
        assert plan[0].lot_id == soon_id  # earliest expiry first
