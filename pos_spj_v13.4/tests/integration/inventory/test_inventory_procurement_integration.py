"""INV-19 — canonical procurement→inventory handlers (§34).

Procurement never writes stock: its goods-receipt / return / reversal events are
consumed here and posted to the canonical ledger, with cost reference, quality
buckets and lot creation. Handlers are idempotent and (until INV-27) parallel to
the legacy path.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.event_handlers.inventory import (
    GoodsReceiptReversedHandler,
    PurchaseReceiptHandler,
    SupplierReturnHandler,
)
from backend.application.inventory.queries import (
    InventoryAvailabilityQueryService,
    TraceabilityQueryService,
)
from backend.domain.inventory.enums import InventoryStatus
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


def _avail(conn, product="p1", status=None):
    dto = InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product, branch_id="b1", warehouse_id="w1")
    if status is None:
        return dto.available
    return Decimal(dto.by_status.get(status, "0"))


def _receipt_payload(**over):
    base = dict(operation_id="gr-1", branch_id="b1", warehouse_id="w1",
                goods_receipt_id="GR-1", supplier_id="sup1", user_id="recv",
                lines=[{"product_id": "p1", "quantity": "10", "unit_cost": "25",
                        "to_location_id": "loc1"}])
    base.update(over)
    return base


class TestPurchaseReceipt:
    def test_receipt_increases_available_with_cost_reference(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        assert _avail(conn) == Decimal("10")
        row = conn.execute(
            "SELECT unit_cost, movement_id FROM inventory_ledger_lines"
            " WHERE product_id='p1'").fetchone()
        assert row["unit_cost"] == "25"  # cost reference carried for Finance
        mv = conn.execute("SELECT movement_type, source_document_type FROM inventory_ledger"
                          " WHERE id=?", (row["movement_id"],)).fetchone()
        assert mv["movement_type"] == "PURCHASE_RECEIPT"
        assert mv["source_document_type"] == "GOODS_RECEIPT"

    def test_quality_hold_lands_in_pending_inspection(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload(quality_hold=True))
        assert _avail(conn) == Decimal("0")  # not sellable
        assert _avail(conn, status=InventoryStatus.PENDING_INSPECTION.value) == Decimal("10")

    def test_lot_coded_line_creates_and_links_lot(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload(lines=[{
            "product_id": "p1", "quantity": "8", "unit_cost": "30",
            "to_location_id": "loc1", "lot_code": "L-77",
            "supplier_lot_code": "SUP-L77", "expiration_date": "2026-12-31"}]))
        lot = conn.execute("SELECT id, supplier_lot_code FROM inventory_lots"
                           " WHERE lot_code='L-77'").fetchone()
        assert lot and lot["supplier_lot_code"] == "SUP-L77"
        line = conn.execute("SELECT lot_id FROM inventory_ledger_lines"
                            " WHERE product_id='p1'").fetchone()
        assert line["lot_id"] == lot["id"]
        # downstream trace derives the receipt from the ledger by lot
        up = TraceabilityQueryService(conn).trace_upstream(lot["id"])
        assert {e.movement_type for e in up.events} == {"PURCHASE_RECEIPT"}

    def test_receipt_is_idempotent(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        PurchaseReceiptHandler(conn).handle(_receipt_payload())  # replay
        assert _avail(conn) == Decimal("10")


class TestSupplierReturnAndReversal:
    def test_supplier_return_decrements(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        SupplierReturnHandler(conn).handle(dict(
            operation_id="ret-1", branch_id="b1", warehouse_id="w1", return_id="RET-1",
            user_id="recv", lines=[{"product_id": "p1", "quantity": "3",
                                    "from_location_id": "loc1"}]))
        assert _avail(conn) == Decimal("7")
        mt = conn.execute("SELECT movement_type FROM inventory_ledger"
                          " WHERE source_document_type='PURCHASE_RETURN'").fetchone()
        assert mt["movement_type"] == "SUPPLIER_RETURN"

    def test_goods_receipt_reversal_backs_out_stock(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        GoodsReceiptReversedHandler(conn).handle(dict(
            operation_id="gr-1", goods_receipt_id="GR-1", user_id="recv",
            reason="proveedor equivocado"))
        assert _avail(conn) == Decimal("0")
        with InventoryUnitOfWork(conn) as uow:
            orig = uow.ledger.list_for_document("GOODS_RECEIPT", "GR-1")[0]
            assert orig["status"] == "REVERSED"

    def test_reversal_is_idempotent(self, conn):
        PurchaseReceiptHandler(conn).handle(_receipt_payload())
        p = dict(operation_id="gr-1", goods_receipt_id="GR-1", user_id="recv")
        GoodsReceiptReversedHandler(conn).handle(p)
        GoodsReceiptReversedHandler(conn).handle(p)  # replay: no double credit
        assert _avail(conn) == Decimal("0")
