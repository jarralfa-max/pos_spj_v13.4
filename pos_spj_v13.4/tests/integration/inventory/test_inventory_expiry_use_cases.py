"""P0-C (§9.4) — expiry alerts + expire-inventory sweep over available lots.

GenerateExpiryAlertsUseCase classifies every AVAILABLE lot's risk and enqueues
INVENTORY_LOT_EXPIRING / INVENTORY_LOT_EXPIRED alerts. ExpireInventoryUseCase
moves past-expiry stock AVAILABLE → EXPIRED so availability excludes it while
on-hand and traceability are preserved.
"""

from datetime import date, timedelta
from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    ExpireInventoryUseCase,
    GenerateExpiryAlertsUseCase,
    PostInventoryMovementUseCase,
    RegisterInventoryLotUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    MovementType,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

TODAY = date(2026, 6, 1)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _lot(conn, code, exp_offset_days, qty="10"):
    exp = (TODAY + timedelta(days=exp_offset_days)).isoformat()
    reg = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code=code, origin_type=LotOrigin.PURCHASE,
        operation_id=f"lot-{code}", actor_user_id="u1", branch_id="b1",
        expiration_date=exp)
    lot_id = reg.entity_id
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                        to_location_id="loc1", lot_id=lot_id)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR",
        source_document_id=f"gr-{code}", operation_id=f"rcv-{code}",
        created_by_user_id="u1", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    return lot_id


def _available(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available


def _bucket(conn, status, lot_id):
    with InventoryUnitOfWork(conn) as uow:
        bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                               inventory_status=status, location_id="loc1",
                               lot_id=lot_id)
        return bal.quantity if bal else Decimal("0")


class TestGenerateExpiryAlerts:
    def test_classifies_and_enqueues_per_risk(self, conn):
        _lot(conn, "OK", 30)          # OK — no alert
        _lot(conn, "WARN", 5)         # within warning_days
        _lot(conn, "CRIT", 1)         # within critical_days
        _lot(conn, "OLD", -3)         # expired
        res = GenerateExpiryAlertsUseCase().execute(
            conn, operation_id="scan-1", actor_user_id="u1", as_of=TODAY,
            warning_days=7, critical_days=2)
        assert res.success
        risks = sorted(a.risk.value for a in res.data["alerts"])
        assert risks == ["CRITICAL", "EXPIRED", "WARNING"]
        with InventoryUnitOfWork(conn) as uow:
            events = sorted(p["event_name"] for p in uow.outbox.list_pending()
                            if p["event_name"].startswith("INVENTORY_LOT_EXPIR"))
        assert events == ["INVENTORY_LOT_EXPIRED", "INVENTORY_LOT_EXPIRING",
                          "INVENTORY_LOT_EXPIRING"]

    def test_no_alerts_when_all_fresh(self, conn):
        _lot(conn, "A", 60)
        res = GenerateExpiryAlertsUseCase().execute(
            conn, operation_id="scan-1", actor_user_id="u1", as_of=TODAY)
        assert res.data["alerts"] == []

    def test_permission_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        res = GenerateExpiryAlertsUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, operation_id="scan-1", actor_user_id="u1", as_of=TODAY)
        assert not res.success and res.error_code == "PERMISSION_DENIED"


class TestExpireInventory:
    def test_moves_expired_stock_to_expired_bucket(self, conn):
        fresh = _lot(conn, "FRESH", 30, "4")
        old = _lot(conn, "OLD", -1, "6")
        assert _available(conn) == Decimal("10")
        res = ExpireInventoryUseCase().execute(
            conn, operation_id="exp-1", actor_user_id="u1", as_of=TODAY)
        assert res.success and res.data["moved"] == 1
        assert res.data["expired_lots"] == 1
        assert _available(conn) == Decimal("4")                       # sólo el fresco
        assert _bucket(conn, InventoryStatus.EXPIRED, old) == Decimal("6")
        assert _bucket(conn, InventoryStatus.AVAILABLE, old) == Decimal("0")
        assert _bucket(conn, InventoryStatus.AVAILABLE, fresh) == Decimal("4")

    def test_idempotent_second_run_is_noop(self, conn):
        _lot(conn, "OLD", -1, "6")
        first = ExpireInventoryUseCase().execute(
            conn, operation_id="exp-1", actor_user_id="u1", as_of=TODAY)
        second = ExpireInventoryUseCase().execute(
            conn, operation_id="exp-1", actor_user_id="u1", as_of=TODAY)
        assert first.data["moved"] == 1
        assert second.data["moved"] == 0
        assert _available(conn) == Decimal("0")

    def test_emits_lot_expired_event(self, conn):
        _lot(conn, "OLD", -1, "6")
        ExpireInventoryUseCase().execute(
            conn, operation_id="exp-1", actor_user_id="u1", as_of=TODAY)
        with InventoryUnitOfWork(conn) as uow:
            events = {p["event_name"] for p in uow.outbox.list_pending()}
        assert "INVENTORY_LOT_EXPIRED" in events

    def test_permission_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        res = ExpireInventoryUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, operation_id="exp-1", actor_user_id="u1", as_of=TODAY)
        assert not res.success and res.error_code == "PERMISSION_DENIED"
