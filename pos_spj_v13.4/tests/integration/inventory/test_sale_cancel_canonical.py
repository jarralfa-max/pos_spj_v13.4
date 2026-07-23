"""INV-27 corte — sale cancellation restores stock to the canonical ledger.

`SalesService.anular_venta` no longer calls the legacy inventory engine directly;
its `_restore_stock_on_cancel` helper posts a canonical SALE_RETURN (→ AVAILABLE)
inside the caller's transaction, idempotent by operation_id.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.services.sales_service import SalesService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


class _Stub:
    def __init__(self, db):
        self.db = db


def _seed(conn, product_id, qty, branch_id="b1"):
    line = InventoryMovementLine.create(
        product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id,
        reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch_id,
        warehouse_id=branch_id, source_module="test", source_document_type="SEED",
        source_document_id="seed", operation_id=f"seed:{product_id}",
        created_by_user_id="system", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="system")


def _available(conn, product_id, branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _cancel(conn, detalles):
    SalesService._restore_stock_on_cancel(
        _Stub(conn), detalles=detalles, branch_id="b1", venta_id="V1",
        folio="F-1", user="cashier")


def test_cancellation_restores_stock_canonically(conn):
    _seed(conn, "p1", "2")            # 8 sold from 10 → 2 left, say
    detalles = [{"producto_id": "p1", "cantidad": 4}]
    _cancel(conn, detalles)
    assert _available(conn, "p1") == Decimal("6")  # 2 + 4 restored
    row = conn.execute("SELECT movement_type FROM inventory_ledger"
                       " WHERE operation_id='sale-cancel:V1'").fetchone()
    assert row["movement_type"] == "SALE_RETURN"


def test_cancellation_is_idempotent(conn):
    _seed(conn, "p1", "2")
    detalles = [{"producto_id": "p1", "cantidad": 4}]
    _cancel(conn, detalles)
    _cancel(conn, detalles)  # re-cancel must not double-restore
    assert _available(conn, "p1") == Decimal("6")


def test_multi_line_cancellation(conn):
    # no prior balance — the SALE_RETURN creates the AVAILABLE bucket
    _cancel(conn, [{"producto_id": "p1", "cantidad": 3},
                   {"producto_id": "p2", "cantidad": 5}])
    assert _available(conn, "p1") == Decimal("3")
    assert _available(conn, "p2") == Decimal("5")
