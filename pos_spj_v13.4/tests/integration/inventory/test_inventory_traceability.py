"""INV-17 — traceability: upstream/downstream derivation + genealogy + recall (§32).

Scenario (meat): a raw chicken lot is received (upstream), consumed in production
(downstream), yielding a cuts lot (genealogy link) that is then sold (downstream).
A recall on the raw lot must reach the sale of the derived cuts lot.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import TraceabilityQueryService
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RegisterTraceabilityLinkUseCase,
)
from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    LotOrigin,
    MovementType,
    TraceabilityLinkType,
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


def _save_lot(conn, *, product_id, lot_code, origin_type, **kwargs):
    lot = InventoryLot.create(product_id=product_id, lot_code=lot_code,
                              origin_type=origin_type, branch_id="b1", **kwargs)
    with InventoryUnitOfWork(conn) as uow:
        uow.lots.save(lot)
    return lot.id


def _post(conn, *, movement_type, op, line):
    mv = InventoryMovement.create(
        movement_type=movement_type, branch_id="b1", warehouse_id="w1",
        source_module="inventory", source_document_type=movement_type.value,
        source_document_id=op, operation_id=op, created_by_user_id="u1", lines=[line])
    res = PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    assert res.success, res.message
    return mv.id


@pytest.fixture
def scenario(conn):
    raw = _save_lot(conn, product_id="chicken_raw", lot_code="RAW-1",
                    origin_type=LotOrigin.PURCHASE, supplier_lot_code="SUP-77")
    cuts = _save_lot(conn, product_id="chicken_cuts", lot_code="CUT-1",
                     origin_type=LotOrigin.PRODUCTION, production_lot_code="PRD-9")
    # raw received (upstream), then consumed in production (downstream)
    _post(conn, movement_type=MovementType.PURCHASE_RECEIPT, op="rcv-raw",
          line=InventoryMovementLine.create(product_id="chicken_raw", quantity=Decimal("10"),
                                            lot_id=raw, to_location_id="loc1"))
    _post(conn, movement_type=MovementType.PRODUCTION_CONSUMPTION, op="con-raw",
          line=InventoryMovementLine.create(product_id="chicken_raw", quantity=Decimal("6"),
                                            lot_id=raw, from_location_id="loc1"))
    # cuts produced (upstream), then sold (downstream)
    _post(conn, movement_type=MovementType.PRODUCTION_OUTPUT, op="out-cut",
          line=InventoryMovementLine.create(product_id="chicken_cuts", quantity=Decimal("6"),
                                            lot_id=cuts, to_location_id="loc2"))
    _post(conn, movement_type=MovementType.SALE_ISSUE, op="sale-cut",
          line=InventoryMovementLine.create(product_id="chicken_cuts", quantity=Decimal("4"),
                                            lot_id=cuts, from_location_id="loc2"))
    # explicit genealogy: raw → cuts
    RegisterTraceabilityLinkUseCase().execute(
        conn, parent_lot_id=raw, child_lot_id=cuts,
        link_type=TraceabilityLinkType.PRODUCTION, operation_id="link-1",
        actor_user_id="u1", quantity=Decimal("6"), product_id="chicken_cuts",
        source_document_type="PRODUCTION_ORDER", source_document_id="po-1")
    return {"raw": raw, "cuts": cuts, "svc": TraceabilityQueryService(conn)}


class TestTraceability:
    def test_upstream_shows_origin_and_receipt(self, scenario):
        dto = scenario["svc"].trace_upstream(scenario["raw"])
        assert dto.direction == "UPSTREAM"
        assert dto.origin["supplier_lot_code"] == "SUP-77"
        assert {e.movement_type for e in dto.events} == {"PURCHASE_RECEIPT"}
        assert all(e.direction == "INCREASE" for e in dto.events)
        assert dto.links == ()  # raw has no explicit parents

    def test_downstream_shows_consumption_and_child_link(self, scenario):
        dto = scenario["svc"].trace_downstream(scenario["raw"])
        assert {e.movement_type for e in dto.events} == {"PRODUCTION_CONSUMPTION"}
        assert all(e.direction == "DECREASE" for e in dto.events)
        assert len(dto.links) == 1 and dto.links[0].child_lot_id == scenario["cuts"]
        assert dto.links[0].link_type == "PRODUCTION"

    def test_child_upstream_reaches_parent_and_output(self, scenario):
        dto = scenario["svc"].trace_upstream(scenario["cuts"])
        assert {e.movement_type for e in dto.events} == {"PRODUCTION_OUTPUT"}
        assert len(dto.links) == 1 and dto.links[0].parent_lot_id == scenario["raw"]

    def test_recall_walks_genealogy_to_the_sale(self, scenario):
        report = scenario["svc"].recall_report(scenario["raw"])
        assert set(report.affected_lot_ids) == {scenario["raw"], scenario["cuts"]}
        types = {e.movement_type for e in report.distribution}
        assert "PRODUCTION_CONSUMPTION" in types and "SALE_ISSUE" in types
        assert report.reaches_customers is True
        assert report.branches_touched == ("b1",)

    def test_link_is_idempotent(self, conn, scenario):
        r = RegisterTraceabilityLinkUseCase().execute(
            conn, parent_lot_id=scenario["raw"], child_lot_id=scenario["cuts"],
            link_type=TraceabilityLinkType.PRODUCTION, operation_id="link-1",
            actor_user_id="u1")
        assert r.success and r.data.get("idempotent") is True

    def test_link_requires_permission(self, conn, scenario):
        class Denies:
            def has_permission(self, u, p):
                return False
        r = RegisterTraceabilityLinkUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, parent_lot_id=scenario["raw"], child_lot_id=scenario["cuts"],
            link_type=TraceabilityLinkType.PRODUCTION, operation_id="link-2",
            actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
