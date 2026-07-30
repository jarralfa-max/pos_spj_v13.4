"""INV-27 / G1 — lecturas agregadas de stock canónico.

`InventoryStockAggregateQueryService` deriva los agregados que los reportes
legacy calculaban sobre `productos.existencia` desde `inventory_balances`
(disponible = quantity − reserved, status AVAILABLE) y el stock bajo desde
`inventory_replenishment_rule.reorder_point`.
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries import (
    InventoryStockAggregateQueryService,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    return c


def _bal(c, pid, branch, wh, qty, reserved="0", status="AVAILABLE"):
    c.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "inventory_status, quantity, reserved_quantity, updated_at) "
        "VALUES (?,?,?,?,?,?,?, datetime('now'))",
        (f"{pid}-{branch}-{wh}-{status}", pid, branch, wh, status, qty, reserved))


def _rule(c, pid, branch, wh, reorder, minq="0"):
    c.execute(
        "INSERT INTO inventory_replenishment_rule (id, product_id, branch_id, "
        "warehouse_id, reorder_point, min_quantity, active, created_at) "
        "VALUES (?,?,?,?,?,?,1, datetime('now'))",
        (f"r-{pid}-{branch}-{wh}", pid, branch, wh, reorder, minq))


def test_available_by_product_sums_across_branches_minus_reserved(conn):
    _bal(conn, "p1", "b1", "w1", "10", reserved="2")
    _bal(conn, "p1", "b2", "w1", "5")
    _bal(conn, "p1", "b1", "w1", "3", status="QUARANTINE")  # no cuenta
    _bal(conn, "p2", "b1", "w1", "7")
    conn.commit()
    svc = InventoryStockAggregateQueryService(conn)
    by_prod = svc.available_by_product()
    assert by_prod["p1"] == Decimal("13")   # (10-2) + 5
    assert by_prod["p2"] == Decimal("7")
    # filtrado por sucursal
    assert svc.available_by_product(branch_id="b2") == {"p1": Decimal("5")}


def test_total_available_scalar(conn):
    _bal(conn, "p1", "b1", "w1", "10", reserved="2")
    _bal(conn, "p1", "b2", "w1", "5")
    conn.commit()
    svc = InventoryStockAggregateQueryService(conn)
    assert svc.total_available(product_id="p1") == Decimal("13")
    assert svc.total_available(product_id="p1", branch_id="b1") == Decimal("8")
    assert svc.total_available(product_id="nope") == Decimal("0")


def test_low_stock_items_vs_reorder_point(conn):
    # p1: disponible 8 en b1, reorder 10 → bajo. p2: disponible 20, reorder 5 → ok.
    _bal(conn, "p1", "b1", "w1", "8")
    _bal(conn, "p2", "b1", "w1", "20")
    _rule(conn, "p1", "b1", "w1", "10", minq="4")
    _rule(conn, "p2", "b1", "w1", "5")
    conn.commit()
    svc = InventoryStockAggregateQueryService(conn)
    items = svc.low_stock_items()
    assert [it.product_id for it in items] == ["p1"]
    assert items[0].available == Decimal("8")
    assert items[0].reorder_point == Decimal("10")
    assert items[0].min_quantity == Decimal("4")
    assert svc.low_stock_count() == 1


def test_low_stock_sums_warehouse_rules_per_branch(conn):
    # dos almacenes: disponible 8 total; reorder 5+5=10 → bajo.
    _bal(conn, "p1", "b1", "w1", "5")
    _bal(conn, "p1", "b1", "w2", "3")
    _rule(conn, "p1", "b1", "w1", "5")
    _rule(conn, "p1", "b1", "w2", "5")
    conn.commit()
    svc = InventoryStockAggregateQueryService(conn)
    items = svc.low_stock_items()
    assert len(items) == 1
    assert items[0].available == Decimal("8") and items[0].reorder_point == Decimal("10")


def test_inactive_rules_are_ignored(conn):
    _bal(conn, "p1", "b1", "w1", "1")
    conn.execute(
        "INSERT INTO inventory_replenishment_rule (id, product_id, branch_id, "
        "warehouse_id, reorder_point, active, created_at) "
        "VALUES ('r0','p1','b1','w1','99',0, datetime('now'))")
    conn.commit()
    assert InventoryStockAggregateQueryService(conn).low_stock_items() == []
