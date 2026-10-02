"""FASE 13 Compras/Costeo (2026-09-28): el promedio móvil usa la EXISTENCIA REAL.

Caso obligatorio del master prompt (§31):

    Compra 100 kg @ $40 → salen 90 kg → quedan 10 kg → compra 10 kg @ $60
    promedio = (10×40 + 10×60) / 20 = $50        (NO $41.82)

$41.82 salía de `tracked_quantity`, que sumaba entradas (100 + 10) y nunca restaba
salidas. Ahora la cantidad previa se le pregunta a Inventario, con movimientos
REALES posteados por `PostInventoryMovementUseCase` (no saldos escritos a mano), y
el resultado no depende de si Inventario procesó la entrada antes o después que
Costeo (ambos escuchan el mismo evento).
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries.costing_stock_query_service import (
    CostingStockQueryService,
)
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.application.pricing.event_handlers.product_cost_projection_handler import (
    ProductCostProjectionHandler,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    create_pricing_schema(c)
    c.execute("ALTER TABLE product_cost ADD COLUMN tracked_quantity TEXT")  # migración 151
    c.commit()
    yield c
    c.close()


def _post(conn, movement_type, qty, op, *, into=True, product="p1", wh="w1"):
    line = (InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                         to_location_id="loc1")
            if into else
            InventoryMovementLine.create(product_id=product, quantity=Decimal(qty),
                                         from_location_id="loc1"))
    movement = InventoryMovement.create(
        movement_type=movement_type, branch_id="b1", warehouse_id=wh,
        source_module="test", source_document_type="DOC", source_document_id=op,
        operation_id=op, created_by_user_id="u1", lines=[line])
    result = PostInventoryMovementUseCase().execute(conn, movement, actor_user_id="u1")
    assert result.success, result.message


def _cost_event(op, *lines):
    return {"event_id": f"evt-{op}", "operation_id": op,
            "lines": [{"product_id": p, "quantity": q, "unit_cost": u} for p, q, u in lines]}


def _average(conn, product="p1") -> Decimal:
    row = conn.execute("SELECT average_cost FROM product_cost WHERE product_id=?"
                       " AND branch_id=''", (product,)).fetchone()
    return Decimal(row[0]).quantize(Decimal("0.01"))


def _receipt(conn, qty, cost, op, *, inventory_first: bool):
    """Una recepción: Inventario y Costeo procesan el MISMO evento, en el orden dado."""
    handler = ProductCostProjectionHandler(conn)
    if inventory_first:
        _post(conn, MovementType.PURCHASE_RECEIPT, qty, op)
        handler.handle(_cost_event(op, ("p1", qty, cost)))
    else:
        handler.handle(_cost_event(op, ("p1", qty, cost)))
        _post(conn, MovementType.PURCHASE_RECEIPT, qty, op)


@pytest.mark.parametrize("inventory_first", [True, False])
def test_mandatory_case_gives_fifty_not_41_82(conn, inventory_first):
    _receipt(conn, "100", "40", "rec-1", inventory_first=inventory_first)
    assert _average(conn) == Decimal("40.00")
    _post(conn, MovementType.SALE_ISSUE, "90", "sale-1", into=False)
    _receipt(conn, "10", "60", "rec-2", inventory_first=inventory_first)
    assert _average(conn) == Decimal("50.00")


def test_selling_everything_then_buying_takes_the_new_cost(conn):
    _receipt(conn, "100", "40", "rec-1", inventory_first=True)
    _post(conn, MovementType.SALE_ISSUE, "100", "sale-1", into=False)
    _receipt(conn, "5", "70", "rec-2", inventory_first=True)
    assert _average(conn) == Decimal("70.00")


def test_waste_counts_as_an_outflow_too(conn):
    _receipt(conn, "50", "20", "rec-1", inventory_first=True)
    _post(conn, MovementType.WASTE, "40", "waste-1", into=False)
    _receipt(conn, "10", "30", "rec-2", inventory_first=True)
    assert _average(conn) == Decimal("25.00")          # (10×20 + 10×30) / 20


def test_stock_in_other_warehouses_counts_because_cost_is_global(conn):
    _post(conn, MovementType.PURCHASE_RECEIPT, "30", "rec-w2", wh="w2")
    ProductCostProjectionHandler(conn).handle(_cost_event("rec-w2", ("p1", "30", "10")))
    _receipt(conn, "10", "50", "rec-w1", inventory_first=True)
    assert _average(conn) == Decimal("20.00")          # (30×10 + 10×50) / 40


def test_two_lines_of_the_same_product_in_one_receipt(conn):
    op = "rec-2lines"
    line_a = InventoryMovementLine.create(product_id="p1", quantity=Decimal("10"),
                                          to_location_id="loc1")
    line_b = InventoryMovementLine.create(product_id="p1", quantity=Decimal("10"),
                                          to_location_id="loc1")
    movement = InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="test", source_document_type="DOC", source_document_id=op,
        operation_id=op, created_by_user_id="u1", lines=[line_a, line_b])
    assert PostInventoryMovementUseCase().execute(conn, movement, actor_user_id="u1").success
    ProductCostProjectionHandler(conn).handle(
        _cost_event(op, ("p1", "10", "40"), ("p1", "10", "60")))
    assert _average(conn) == Decimal("50.00")


def test_replaying_the_event_does_not_move_the_average(conn):
    _receipt(conn, "100", "40", "rec-1", inventory_first=True)
    _post(conn, MovementType.SALE_ISSUE, "90", "sale-1", into=False)
    _receipt(conn, "10", "60", "rec-2", inventory_first=True)
    ProductCostProjectionHandler(conn).handle(_cost_event("rec-2", ("p1", "10", "60")))
    assert _average(conn) == Decimal("50.00")


def test_stock_query_is_prior_to_the_entry_in_either_order(conn):
    stock = CostingStockQueryService(conn)
    _post(conn, MovementType.PURCHASE_RECEIPT, "100", "rec-1")
    assert stock.on_hand_before("p1", operation_id="rec-2") == Decimal("100")  # aún no entra
    _post(conn, MovementType.PURCHASE_RECEIPT, "10", "rec-2")
    assert stock.on_hand_before("p1", operation_id="rec-2") == Decimal("100")  # ya entró
    assert stock.on_hand_before("otro", operation_id="rec-2") == Decimal("0")


def test_without_canonical_inventory_it_falls_back_to_the_old_counter():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_pricing_schema(c)
    c.execute("ALTER TABLE product_cost ADD COLUMN tracked_quantity TEXT")
    assert CostingStockQueryService(c).on_hand_before("p1", operation_id="x") is None
    handler = ProductCostProjectionHandler(c)
    handler.handle(_cost_event("a", ("p1", "10", "10")))
    handler.handle(_cost_event("b", ("p1", "10", "30")))
    assert _average(c) == Decimal("20.00")
