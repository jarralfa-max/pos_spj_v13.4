from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from core.services.sales_fulfillment_service import SaleFulfillmentService
from core.services.sales_service import SalesService


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, tipo_producto TEXT DEFAULT 'simple', es_compuesto INTEGER DEFAULT 0, es_subproducto INTEGER DEFAULT 0, existencia REAL DEFAULT 0);
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, cantidad REAL DEFAULT 0, rendimiento_pct REAL DEFAULT 0, orden INTEGER DEFAULT 0);
        CREATE TABLE branch_inventory (product_id INTEGER, branch_id INTEGER, quantity REAL DEFAULT 0);
        """
    )
    return c


def test_modes_direct_composite_virtual_and_missing():
    db = _db()
    db.executescript(
        """
        INSERT INTO productos(id,nombre,tipo_producto,es_compuesto,es_subproducto,existencia) VALUES
          (1,'Simple','simple',0,0,0),(2,'Comp','compuesto',1,0,0),(3,'A','simple',0,0,0),(4,'B','simple',0,0,0),
          (5,'Proc','procesable',0,1,0),(6,'Pechuga','simple',0,0,0);
        INSERT INTO product_recipes(id,product_id,tipo_receta,is_active) VALUES (10,2,'COMBINACION',1),(20,5,'COMBINACION',1);
        INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,orden) VALUES (10,3,1,0),(10,4,0.5,1),(20,6,1,0);
        INSERT INTO branch_inventory(product_id,branch_id,quantity) VALUES (1,1,5),(3,1,10),(4,1,10),(6,1,10);
        """
    )
    svc = SaleFulfillmentService(db)
    assert svc.resolve_item(1, 2, 1)[0].mode == "DIRECT"
    comp = svc.resolve_item(2, 2, 1)
    assert sum(x.qty for x in comp if x.product_id == 3) == 2
    assert any(x.mode == "COMPOSITE" for x in comp)
    virt = svc.resolve_item(5, 1, 1)
    assert any(x.mode == "VIRTUAL_FROM_COMPONENTS" for x in virt)
    try:
        svc.resolve_item(1, 50, 1)
        assert False, "debió fallar"
    except ValueError as e:
        assert "STOCK_INSUFICIENTE" in str(e)


def test_sales_service_ignores_ui_es_compuesto_and_publishes_resolved_items(monkeypatch):
    db = _db()
    db.executescript(
        """
        INSERT INTO productos(id,nombre,tipo_producto,es_compuesto,existencia) VALUES (2,'Comp','compuesto',1,0),(3,'A','simple',0,0);
        INSERT INTO product_recipes(id,product_id,tipo_receta,is_active) VALUES (10,2,'COMBINACION',1);
        INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,orden) VALUES (10,3,2,0);
        INSERT INTO branch_inventory(product_id,branch_id,quantity) VALUES (3,1,20);
        """
    )
    captured = {}
    class _Bus:
        def publish(self, evt, payload, strict=False):
            captured["evt"] = evt
            captured["payload"] = payload
    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())

    sales_repo = SimpleNamespace(
        create_sale=lambda **kwargs: (1, "F-1"),
        save_sale_item=lambda **kwargs: None,
    )
    svc = SalesService(db, sales_repo, None, None, None, None, None, None, None, None, None, None)
    folio, _ = svc.execute_sale(
        branch_id=1, user="u",
        items=[{"product_id": 2, "qty": 3, "unit_price": 10, "es_compuesto": 0, "nombre": "Comp"}],
        payment_method="Efectivo", amount_paid=100
    )
    assert folio == "F-1"
    itm = captured["payload"]["items"]
    assert len(itm) == 1
    assert itm[0]["product_id"] == 3 and abs(itm[0]["qty"] - 6.0) < 1e-9
