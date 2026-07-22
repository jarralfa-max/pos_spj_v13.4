"""INV-18 — replenishment generation: purchase vs transfer, idempotency, perms (§34)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import ReplenishmentQueryService
from backend.application.inventory.use_cases import (
    GenerateReplenishmentSuggestionsUseCase,
    PostInventoryMovementUseCase,
    SetReplenishmentRuleUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType, ReplenishmentSource
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _receive(conn, *, product, warehouse, qty, op, branch="b1"):
    line = InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                        to_location_id=f"{warehouse}-loc")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id=branch,
        warehouse_id=warehouse, source_module="procurement", source_document_type="GR",
        source_document_id=op, operation_id=op, created_by_user_id="u1", lines=[line])
    assert PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1").success


def _rule(conn, **kw):
    return SetReplenishmentRuleUseCase().execute(conn, actor_user_id="mgr", **kw)


class TestReplenishmentGeneration:
    def test_purchase_suggestion_when_below_reorder(self, conn):
        _rule(conn, product_id="p1", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("10"), target_quantity=Decimal("30"),
              safety_stock=Decimal("3"))
        _receive(conn, product="p1", warehouse="w1", qty="5", op="rcv-p1")
        res = GenerateReplenishmentSuggestionsUseCase().execute(
            conn, operation_id="run-1", actor_user_id="planner", branch_id="b1")
        assert res.success and res.data["count"] == 1
        sug = ReplenishmentQueryService(conn).list_open_suggestions(branch_id="b1")
        assert len(sug) == 1
        assert sug[0]["source_type"] == "PURCHASE"
        assert sug[0]["suggested_quantity"] == "25" and sug[0]["urgency"] == "REORDER"

    def test_transfer_suggestion_when_source_has_surplus(self, conn):
        _rule(conn, product_id="p2", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("10"), target_quantity=Decimal("20"),
              preferred_source=ReplenishmentSource.TRANSFER, source_warehouse_id="w2")
        _receive(conn, product="p2", warehouse="w1", qty="4", op="rcv-p2-w1")
        _receive(conn, product="p2", warehouse="w2", qty="50", op="rcv-p2-w2")
        GenerateReplenishmentSuggestionsUseCase().execute(
            conn, operation_id="run-2", actor_user_id="planner")
        sug = ReplenishmentQueryService(conn).list_open_suggestions()
        row = next(s for s in sug if s["product_id"] == "p2")
        assert row["source_type"] == "TRANSFER" and row["source_warehouse_id"] == "w2"
        assert row["suggested_quantity"] == "16"

    def test_no_suggestion_when_above_reorder(self, conn):
        _rule(conn, product_id="p3", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("10"), target_quantity=Decimal("30"))
        _receive(conn, product="p3", warehouse="w1", qty="25", op="rcv-p3")
        res = GenerateReplenishmentSuggestionsUseCase().execute(
            conn, operation_id="run-3", actor_user_id="planner", branch_id="b1")
        assert res.success and res.data["count"] == 0

    def test_generation_is_idempotent(self, conn):
        _rule(conn, product_id="p1", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("10"), target_quantity=Decimal("30"))
        _receive(conn, product="p1", warehouse="w1", qty="2", op="rcv")
        GenerateReplenishmentSuggestionsUseCase().execute(
            conn, operation_id="run-x", actor_user_id="planner")
        again = GenerateReplenishmentSuggestionsUseCase().execute(
            conn, operation_id="run-x", actor_user_id="planner")
        assert again.success and again.data.get("idempotent") is True
        assert len(ReplenishmentQueryService(conn).list_open_suggestions()) == 1

    def test_rule_upsert_updates_in_place(self, conn):
        _rule(conn, product_id="p1", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("10"), target_quantity=Decimal("30"))
        _rule(conn, product_id="p1", branch_id="b1", warehouse_id="w1",
              reorder_point=Decimal("15"), target_quantity=Decimal("40"))
        rules = ReplenishmentQueryService(conn).list_rules(branch_id="b1")
        assert len(rules) == 1 and rules[0]["reorder_point"] == "15"

    def test_manage_requires_permission(self, conn):
        class Denies:
            def has_permission(self, u, p):
                return False
        r = SetReplenishmentRuleUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, product_id="p1", branch_id="b1", warehouse_id="w1",
            reorder_point=Decimal("10"), target_quantity=Decimal("30"),
            actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_generate_requires_permission(self, conn):
        class Denies:
            def has_permission(self, u, p):
                return False
        r = GenerateReplenishmentSuggestionsUseCase(
            InventoryAuthorizationPolicy(Denies())).execute(
            conn, operation_id="run-z", actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
