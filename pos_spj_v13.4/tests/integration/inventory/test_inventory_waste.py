"""INV-16 — classified waste/disposal: distinct movements, theoretical, event, perms."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RegisterWasteUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType, WasteType
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


def _waste(conn, wtype, qty="2", op="w-1", user="clerk"):
    return RegisterWasteUseCase().execute(
        conn, product_id="p1", branch_id="b1", warehouse_id="w1", waste_type=wtype,
        quantity=Decimal(qty), operation_id=op, actor_user_id=user, location_id="loc1",
        reason_note="test")


class TestWaste:
    def test_actual_waste_decrements_and_records(self, conn):
        _seed(conn, "10")
        r = _waste(conn, WasteType.DAMAGE, "3")
        assert r.success and not r.data["is_theoretical"]
        assert _avail(conn) == Decimal("7")
        with InventoryUnitOfWork(conn) as uow:
            rows = uow.waste.list_for_product("p1", "b1")
            assert rows and rows[0]["waste_type"] == "DAMAGE" and rows[0]["movement_id"]
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert "INVENTORY_WASTE_RECORDED" in events

    def test_shrinkage_and_expiry_use_distinct_movement_types(self, conn):
        _seed(conn, "10")
        _waste(conn, WasteType.SHRINKAGE, "1", op="w-shr")
        _waste(conn, WasteType.EXPIRY, "2", op="w-exp", user="qa")  # disposal-class perm
        assert _avail(conn) == Decimal("7")
        types = {r["movement_type"] for r in conn.execute(
            "SELECT movement_type FROM inventory_ledger WHERE source_document_type='WASTE'"
        ).fetchall()}
        assert "SHRINKAGE" in types and "EXPIRY_DISPOSAL" in types

    def test_theoretical_waste_records_without_movement(self, conn):
        _seed(conn, "10")
        r = _waste(conn, WasteType.THEORETICAL_WASTE, "2")
        assert r.success and r.data["is_theoretical"] and r.data["movement_id"] is None
        assert _avail(conn) == Decimal("10")  # no physical exit
        with InventoryUnitOfWork(conn) as uow:
            rows = uow.waste.list_for_product("p1", "b1")
            assert rows[0]["is_theoretical"] == 1 and rows[0]["movement_id"] is None

    def test_disposal_requires_disposal_permission(self, conn):
        _seed(conn, "10")
        class OnlyMovement:
            def has_permission(self, u, p):
                return p != "INVENTORY_DISPOSAL_AUTHORIZE"
        r = RegisterWasteUseCase(InventoryAuthorizationPolicy(OnlyMovement())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            waste_type=WasteType.CONDEMNATION, quantity=Decimal("2"), operation_id="w-1",
            actor_user_id="clerk", location_id="loc1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_waste_beyond_stock_rolls_back(self, conn):
        _seed(conn, "2")
        r = _waste(conn, WasteType.DAMAGE, "5")
        assert not r.success and r.error_code == "INVENTORY_RULE_VIOLATION"
        assert _avail(conn) == Decimal("2")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.waste.list_for_product("p1", "b1") == []
