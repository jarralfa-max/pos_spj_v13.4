"""INV/PROD — enabler de stock bajo canónico (migración 168 + G1 nivel producto).

168 respalda una regla de reposición global (`branch_id=''`) por producto activo
con `reorder_point=stock_minimo`; `InventoryStockAggregateQueryService.low_stock_
products` compara el disponible total del producto contra ese umbral —
equivalente canónico de `existencia <= stock_minimo`.
"""

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.queries import InventoryStockAggregateQueryService
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

_168 = importlib.import_module(
    "migrations.standalone.168_replenishment_reorder_from_stock_minimo")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.execute("CREATE TABLE productos (id TEXT PRIMARY KEY, stock_minimo REAL, "
              "activo INTEGER DEFAULT 1)")
    return c


def _bal(c, pid, branch, qty):
    c.execute(
        "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id, "
        "inventory_status, quantity, reserved_quantity, updated_at) "
        "VALUES (?,?,?, 'w1', 'AVAILABLE', ?, '0', datetime('now'))",
        (f"{pid}-{branch}", pid, branch, qty))


def test_168_backfills_global_rule_per_active_product(conn):
    conn.execute("INSERT INTO productos VALUES ('p1', 10, 1)")
    conn.execute("INSERT INTO productos VALUES ('p2', 5, 1)")
    conn.execute("INSERT INTO productos VALUES ('p3', 8, 0)")  # inactivo → sin regla
    conn.commit()
    _168.run(conn)
    rules = conn.execute(
        "SELECT product_id, reorder_point, branch_id, warehouse_id "
        "FROM inventory_replenishment_rule ORDER BY product_id").fetchall()
    assert [r["product_id"] for r in rules] == ["p1", "p2"]
    assert rules[0]["reorder_point"] == "10.0" and rules[0]["branch_id"] == ""


def test_168_is_idempotent_and_preserves_existing_rule(conn):
    conn.execute("INSERT INTO productos VALUES ('p1', 10, 1)")
    conn.execute("INSERT INTO inventory_replenishment_rule (id, product_id, branch_id,"
                 " warehouse_id, reorder_point, active, created_at) "
                 "VALUES ('manual','p1','','','99',1, datetime('now'))")
    conn.commit()
    _168.run(conn); _168.run(conn)
    rows = conn.execute("SELECT reorder_point FROM inventory_replenishment_rule "
                        "WHERE product_id='p1' AND branch_id=''").fetchall()
    assert len(rows) == 1 and rows[0]["reorder_point"] == "99"  # no sobreescribe


def test_low_stock_products_equivalent_to_legacy(conn):
    # p1: min 10, disponible 8 (b1) + 0 → 8 ≤ 10 → bajo.
    # p2: min 5, disponible 20 → no.
    # p3: min 0, disponible 0 → 0 ≤ 0 → bajo (pero excluido con positive_only).
    conn.execute("INSERT INTO productos VALUES ('p1', 10, 1)")
    conn.execute("INSERT INTO productos VALUES ('p2', 5, 1)")
    conn.execute("INSERT INTO productos VALUES ('p3', 0, 1)")
    _bal(conn, "p1", "b1", "8")
    _bal(conn, "p2", "b1", "20")
    conn.commit()
    _168.run(conn)
    svc = InventoryStockAggregateQueryService(conn)
    assert [it.product_id for it in svc.low_stock_products()] == ["p1", "p3"]
    assert svc.low_stock_products_count() == 2
    # con umbral positivo (equivalente a stock_minimo > 0 del motor de alertas)
    assert [it.product_id for it in
            svc.low_stock_products(positive_threshold_only=True)] == ["p1"]
    assert svc.low_stock_products_count(positive_threshold_only=True) == 1
    p1 = svc.low_stock_products()[0]
    assert p1.available == Decimal("8") and p1.reorder_point == Decimal("10.0")
