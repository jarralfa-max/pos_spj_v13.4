"""INV-20 — canonical production→inventory handler (§34).

A production run consumes raw material and yields a finished good plus co-/by-
products; the yield gap is implicit merma. Outputs get lots + genealogy back to
the consumed inputs (recall). WIP outputs land non-sellable. Idempotent.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory import ProductionExecutionHandler
from backend.application.inventory.queries import (
    InventoryAvailabilityQueryService,
    TraceabilityQueryService,
)
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, LotOrigin, MovementType
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


def _seed_stock(conn, *, product, qty, lot_id=None, op):
    line = InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                        lot_id=lot_id, to_location_id="raw-loc")
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GR", source_document_id=op,
        operation_id=op, created_by_user_id="u1", lines=[line])
    assert PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1").success


def _save_lot(conn, *, product, code, origin=LotOrigin.PURCHASE):
    lot = InventoryLot.create(product_id=product, lot_code=code, origin_type=origin,
                              branch_id="b1")
    with InventoryUnitOfWork(conn) as uow:
        uow.lots.save(lot)
    return lot.id


def _avail(conn, product, status=None):
    dto = InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product, branch_id="b1", warehouse_id="w1")
    if status is None:
        return dto.available
    return Decimal(dto.by_status.get(status, "0"))


class TestProduction:
    def test_consumes_inputs_and_produces_classified_outputs(self, conn):
        _seed_stock(conn, product="flour", qty="100", op="s1")
        ProductionExecutionHandler(conn).handle(dict(
            operation_id="prod-1", branch_id="b1", warehouse_id="w1",
            production_id="PO-1", user_id="baker",
            consumptions=[{"product_id": "flour", "quantity": "80",
                           "from_location_id": "raw-loc"}],
            outputs=[
                {"product_id": "bread", "quantity": "60", "output_type": "FINISHED",
                 "to_location_id": "fg-loc", "unit_cost": "5"},
                {"product_id": "crumbs", "quantity": "5", "output_type": "BY_PRODUCT",
                 "to_location_id": "fg-loc"},
            ]))
        assert _avail(conn, "flour") == Decimal("20")     # 100 - 80 consumed
        assert _avail(conn, "bread") == Decimal("60")
        assert _avail(conn, "crumbs") == Decimal("5")     # by-product is stock
        # merma (80 in → 65 out) is implicit; no phantom stock exists for it
        types = {r["movement_type"] for r in conn.execute(
            "SELECT movement_type FROM inventory_ledger WHERE source_module='production'"
        ).fetchall()}
        assert types == {"PRODUCTION_CONSUMPTION", "PRODUCTION_OUTPUT"}

    def test_output_lot_links_genealogy_to_input_lot(self, conn):
        raw = _save_lot(conn, product="flour", code="RAW-1")
        _seed_stock(conn, product="flour", qty="50", lot_id=raw, op="s2")
        ProductionExecutionHandler(conn).handle(dict(
            operation_id="prod-2", branch_id="b1", warehouse_id="w1",
            production_id="PO-2", user_id="baker",
            consumptions=[{"product_id": "flour", "quantity": "40", "lot_id": raw,
                           "from_location_id": "raw-loc"}],
            outputs=[{"product_id": "bread", "quantity": "30", "output_type": "FINISHED",
                      "lot_code": "BREAD-1", "to_location_id": "fg-loc"}]))
        child = conn.execute("SELECT id FROM inventory_lots WHERE lot_code='BREAD-1'").fetchone()
        assert child is not None
        # recall on the raw lot reaches the finished-good lot
        report = TraceabilityQueryService(conn).recall_report(raw)
        assert child["id"] in report.affected_lot_ids

    def test_wip_outputs_are_not_sellable(self, conn):
        _seed_stock(conn, product="flour", qty="100", op="s3")
        ProductionExecutionHandler(conn).handle(dict(
            operation_id="prod-3", branch_id="b1", warehouse_id="w1",
            production_id="PO-3", user_id="baker", wip=True,
            consumptions=[{"product_id": "flour", "quantity": "50",
                           "from_location_id": "raw-loc"}],
            outputs=[{"product_id": "dough", "quantity": "45", "output_type": "FINISHED",
                      "to_location_id": "wip-loc"}]))
        assert _avail(conn, "dough") == Decimal("0")   # held, not sellable
        assert _avail(conn, "dough", InventoryStatus.PRODUCTION_HOLD.value) == Decimal("45")

    def test_is_idempotent(self, conn):
        _seed_stock(conn, product="flour", qty="100", op="s4")
        payload = dict(operation_id="prod-4", branch_id="b1", warehouse_id="w1",
                       production_id="PO-4", user_id="baker",
                       consumptions=[{"product_id": "flour", "quantity": "30",
                                      "from_location_id": "raw-loc"}],
                       outputs=[{"product_id": "bread", "quantity": "25",
                                 "output_type": "FINISHED", "to_location_id": "fg-loc"}])
        ProductionExecutionHandler(conn).handle(payload)
        ProductionExecutionHandler(conn).handle(payload)  # replay
        assert _avail(conn, "flour") == Decimal("70")
        assert _avail(conn, "bread") == Decimal("25")
