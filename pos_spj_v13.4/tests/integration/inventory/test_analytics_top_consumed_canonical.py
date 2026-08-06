"""P2 repoint — AnalyticsEngine.inventory_intelligence reads the canonical ledger.

``top_consumed`` (the "most-consumed products in the last 30 days" BI metric)
queried the legacy ``movimientos_inventario`` table (``tipo='SALIDA'``); it now
reads the canonical ``inventory_ledger``/``inventory_ledger_lines``, summing the
canonical movement types with DECREASE direction (sale issue, transfer dispatch,
production consumption, adjustment out, waste, shrinkage, expiry disposal,
supplier return). The method had zero callers when audited (dead but live-class
code); this repoint keeps its query correct without changing its public contract.
"""

from decimal import Decimal

import sqlite3

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.services.analytics.analytics_engine import AnalyticsEngine


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    return c


def _seed_stock(conn, *, branch_id, product_id, qty, op_id):
    line = InventoryMovementLine.create(
        product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id)
    mv = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id=branch_id,
        warehouse_id=branch_id, source_module="test", source_document_type="TEST",
        source_document_id=op_id, operation_id=op_id, created_by_user_id="u1",
        lines=[line])
    result = PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    assert result.success, result.message


def _post(conn, *, movement_type, branch_id, product_id, qty, op_id):
    if movement_type in (MovementType.SALE_ISSUE, MovementType.ADJUSTMENT_OUT,
                        MovementType.WASTE):
        line = InventoryMovementLine.create(
            product_id=product_id, quantity=Decimal(qty), from_location_id=branch_id)
    else:
        line = InventoryMovementLine.create(
            product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id)
    mv = InventoryMovement.create(
        movement_type=movement_type, branch_id=branch_id, warehouse_id=branch_id,
        source_module="test", source_document_type="TEST", source_document_id=op_id,
        operation_id=op_id, created_by_user_id="u1", lines=[line])
    result = PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
    assert result.success, result.message


def test_top_consumed_sums_canonical_decrease_movements():
    conn = _conn()
    _seed_stock(conn, branch_id="b1", product_id="p1", qty="50", op_id="seed-p1")
    _seed_stock(conn, branch_id="b1", product_id="p2", qty="100", op_id="seed-p2")
    # p1: dos salidas (venta + ajuste) en b1 → deben sumarse
    _post(conn, movement_type=MovementType.SALE_ISSUE, branch_id="b1",
          product_id="p1", qty="5", op_id="op-1")
    _post(conn, movement_type=MovementType.ADJUSTMENT_OUT, branch_id="b1",
          product_id="p1", qty="3", op_id="op-2")

    result = AnalyticsEngine(conn).inventory_intelligence(sucursal_id="b1", top=10)
    top = {r["producto_id"]: r["total_consumido"] for r in result["top_consumed"]}
    assert top.get("p1") == 8.0     # 5 + 3, sólo movimientos de salida
    assert "p2" not in top          # la recepción (INCREASE) no cuenta


def test_top_consumed_scoped_to_branch():
    conn = _conn()
    _seed_stock(conn, branch_id="b1", product_id="p1", qty="50", op_id="seed-b1")
    _seed_stock(conn, branch_id="b9", product_id="p1", qty="200", op_id="seed-b9")
    _post(conn, movement_type=MovementType.SALE_ISSUE, branch_id="b1",
          product_id="p1", qty="5", op_id="op-1")
    _post(conn, movement_type=MovementType.SALE_ISSUE, branch_id="b9",
          product_id="p1", qty="99", op_id="op-9")
    result = AnalyticsEngine(conn).inventory_intelligence(sucursal_id="b1", top=10)
    top = {r["producto_id"]: r["total_consumido"] for r in result["top_consumed"]}
    assert top.get("p1") == 5.0  # la sucursal ajena no debe sumarse
