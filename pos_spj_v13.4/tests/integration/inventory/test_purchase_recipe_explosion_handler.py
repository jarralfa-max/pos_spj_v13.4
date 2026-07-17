"""PUR-13 step 2d — PurchaseRecipeExplosionHandler consumes components on purchase.

Migrated from the monolith's _procesar_recetas: buying a product with an active
recipe deducts each component (cantidad_insumo × qty) via a 'salida' movement.
Idempotent per (event, product). Products without a recipe deduct nothing.
"""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.event_handlers.inventory.purchase_recipe_explosion_handler import (
    PurchaseRecipeExplosionHandler,
)


@pytest.fixture
def inv_conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY, producto_id TEXT,"
        " sucursal_id TEXT, cantidad REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id))")
    c.execute(
        "CREATE TABLE movimientos_inventario (id TEXT PRIMARY KEY, producto_id TEXT,"
        " tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia TEXT,"
        " referencia_id TEXT, referencia_tipo TEXT, usuario TEXT, sucursal_id TEXT)")
    c.execute("""
        CREATE TRIGGER trg AFTER INSERT ON movimientos_inventario
        WHEN NEW.producto_id IS NOT NULL AND NEW.sucursal_id IS NOT NULL BEGIN
          INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)
          VALUES (NEW.producto_id, NEW.sucursal_id,
            CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END)
          ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
            cantidad = inventario_actual.cantidad +
              CASE WHEN NEW.tipo IN ('entrada','COMPRA') THEN NEW.cantidad ELSE -NEW.cantidad END;
        END""")
    # recipe schema: product 'marinado' consumes 1 'pollo_crudo' + 0.05 'adobo' per unit
    c.execute("CREATE TABLE recetas (id TEXT PRIMARY KEY, producto_id TEXT,"
              " producto_base_id TEXT, activa INTEGER DEFAULT 1, activo INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE receta_componentes (id TEXT PRIMARY KEY, receta_id TEXT,"
              " producto_id TEXT, cantidad REAL)")
    c.execute("INSERT INTO recetas (id, producto_id) VALUES ('r1','marinado')")
    c.execute("INSERT INTO receta_componentes VALUES ('c1','r1','pollo_crudo',1)")
    c.execute("INSERT INTO receta_componentes VALUES ('c2','r1','adobo',0.05)")
    # seed component stock
    for comp, qty in (("pollo_crudo", 100.0), ("adobo", 10.0)):
        c.execute("INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad)"
                  " VALUES (?, 'wh-1', ?)", (comp, qty))
    c.commit()
    yield c
    c.close()


def _event(lines, event_id="e1"):
    return {"event_id": event_id, "warehouse_id": "wh-1", "user_id": "prod", "lines": lines}


def _stock(conn, pid):
    return Decimal(str(conn.execute(
        "SELECT cantidad FROM inventario_actual WHERE producto_id=? AND sucursal_id='wh-1'",
        (pid,)).fetchone()[0]))


def test_recipe_deducts_components(inv_conn):
    PurchaseRecipeExplosionHandler(inv_conn).handle(_event(
        [{"product_id": "marinado", "quantity": "10", "unit_cost": "60"}]))
    # 10 units → 10 pollo_crudo + 0.5 adobo consumed
    assert _stock(inv_conn, "pollo_crudo") == Decimal("90")
    assert _stock(inv_conn, "adobo") == Decimal("9.5")


def test_product_without_recipe_deducts_nothing(inv_conn):
    PurchaseRecipeExplosionHandler(inv_conn).handle(_event(
        [{"product_id": "caja", "quantity": "5", "unit_cost": "8"}]))
    assert inv_conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0] == 0


def test_idempotent_per_event_and_product(inv_conn):
    ev = _event([{"product_id": "marinado", "quantity": "10", "unit_cost": "60"}], event_id="dup")
    PurchaseRecipeExplosionHandler(inv_conn).handle(ev)
    PurchaseRecipeExplosionHandler(inv_conn).handle(ev)  # replay
    assert _stock(inv_conn, "pollo_crudo") == Decimal("90")  # not double-deducted
    moves = inv_conn.execute("SELECT COUNT(*) FROM movimientos_inventario").fetchone()[0]
    assert moves == 2  # one per component, once
