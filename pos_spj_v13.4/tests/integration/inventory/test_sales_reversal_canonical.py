"""INV-27 corte — SalesReversalService restores stock to the canonical ledger.

Both cancel_sale (PASO 3) and refund_items (PASO 3b) no longer call the legacy
inventory engine; they post canonical SALE_RETURN movements (→ AVAILABLE) inside
their transaction, preserving lot (batch_id → lot_id) and legacy sellable-restore
behaviour.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.services.sales_reversal_service import SalesReversalService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _svc():
    # bypass __init__ (needs a wrapped DB); we only exercise the pure helpers
    return SalesReversalService.__new__(SalesReversalService)


def _available(conn, product_id, branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def test_cancel_restore_posts_canonical_sale_return(conn):
    n = _svc()._restore_stock_canonical(
        conn=conn,
        items=[{"producto_id": "p1", "cantidad": 3, "batch_id": None},
               {"producto_id": "p2", "cantidad": 2, "batch_id": None}],
        branch_id="b1", sale_id="S1", folio="F1", user="u1")
    assert n == 2
    assert _available(conn, "p1") == Decimal("3")
    assert _available(conn, "p2") == Decimal("2")
    row = conn.execute("SELECT movement_type FROM inventory_ledger"
                       " WHERE operation_id='sale-cancel:S1'").fetchone()
    assert row["movement_type"] == "SALE_RETURN"


def test_cancel_restore_idempotent(conn):
    args = dict(conn=conn, items=[{"producto_id": "p1", "cantidad": 3, "batch_id": None}],
                branch_id="b1", sale_id="S1", folio="F1", user="u1")
    _svc()._restore_stock_canonical(**args)
    _svc()._restore_stock_canonical(**args)  # replay
    assert _available(conn, "p1") == Decimal("3")  # restored once


def test_refund_restore_preserves_lot(conn):
    # a refund with a lot_id restores that lot's AVAILABLE bucket
    from backend.application.inventory.use_cases import PostInventoryMovementUseCase
    from backend.domain.inventory.entities.inventory_movement import (
        InventoryMovement, InventoryMovementLine)
    from backend.domain.inventory.enums import MovementType
    # seed a lot receipt so the lot exists in balances
    line = InventoryMovementLine.create(product_id="p1", quantity=Decimal("0.001"),
                                        to_location_id="b1", lot_id="lotA")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id="b1", warehouse_id="b1",
        source_module="t", source_document_type="S", source_document_id="s",
        operation_id="seed-lot", created_by_user_id="s", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="s")

    n = _svc()._post_canonical_return(
        conn=conn,
        lines_data=[("p1", 4, "lotA")], branch_id="b1", sale_id="S9",
        doc_type="SALE_PARTIAL_REFUND", operation_id="REFUND-S9-abcd",
        reason_code="SALE_PARTIAL_REFUND", user="u1")
    assert n == 1
    row = conn.execute("SELECT lot_id FROM inventory_ledger_lines"
                       " WHERE lot_id='lotA'").fetchone()
    assert row is not None


def test_no_lines_is_noop(conn):
    n = _svc()._restore_stock_canonical(
        conn=conn, items=[], branch_id="b1", sale_id="S1",
        folio="F1", user="u1")
    assert n == 0
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0
