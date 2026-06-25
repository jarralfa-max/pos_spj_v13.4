from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from core.services.recipe_engine import RecipeEngine
from core.services.sales_service import SalesService


def test_sale_payload_has_fulfillment_trace(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, tipo_producto TEXT DEFAULT 'simple', es_compuesto INTEGER DEFAULT 0, es_subproducto INTEGER DEFAULT 0, existencia REAL DEFAULT 0);
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, cantidad REAL DEFAULT 0, rendimiento_pct REAL DEFAULT 0, orden INTEGER DEFAULT 0);
        CREATE TABLE branch_inventory (product_id INTEGER, branch_id INTEGER, quantity REAL DEFAULT 0);
        CREATE TABLE inventory_stock (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, quantity REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(product_id, branch_id));
        INSERT INTO productos VALUES (10,'Combo','compuesto',1,0,0),(11,'CompA','simple',0,0,0);
        INSERT INTO product_recipes VALUES (1,10,'COMBINACION',1);
        INSERT INTO product_recipe_components(id,recipe_id,component_product_id,cantidad,orden) VALUES (1,1,11,2,0);
        INSERT INTO branch_inventory VALUES (11,1,100);
        INSERT INTO inventory_stock(id,product_id,branch_id,quantity) VALUES ('s11','11','1',100);
        """
    )
    cap = {}
    class _Bus:
        def publish(self, evt, payload, strict=False):
            cap["payload"] = payload
    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())
    repo = SimpleNamespace(create_sale=lambda **k: (1, "F1"), save_sale_item=lambda **k: None)
    svc = SalesService(db, repo, None, None, None, None, None, None, None, None, None, None)
    svc.execute_sale(1, "u", [{"product_id": 10, "qty": 3, "unit_price": 10, "nombre": "Combo"}], "Efectivo", 100)
    i = cap["payload"]["items"][0]
    assert i["sold_product_id"] == 10
    assert i["source_product_id"] == 10
    assert i["fulfillment_mode"] == "COMPOSITE"
    assert i["product_id"] == 11 and abs(i["qty"] - 6.0) < 1e-9


def test_production_cost_ledger_has_waste_line(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg', precio_compra REAL DEFAULT 0, costo REAL DEFAULT 0);
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, nombre_receta TEXT, unidad_base TEXT DEFAULT 'kg', peso_promedio_kg REAL DEFAULT 1, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, rendimiento_pct REAL DEFAULT 0, merma_pct REAL DEFAULT 0, factor_costo REAL DEFAULT 1.0, unidad TEXT DEFAULT 'kg', orden INTEGER DEFAULT 0, tolerancia_pct REAL DEFAULT 2.0);
        CREATE TABLE producciones (id TEXT PRIMARY KEY, receta_id INTEGER, producto_base_id INTEGER, cantidad_base REAL, unidad_base TEXT, usuario TEXT, sucursal_id INTEGER, notas TEXT, estado TEXT, fecha TEXT, operation_id TEXT UNIQUE);
        CREATE TABLE produccion_detalle (id TEXT PRIMARY KEY, produccion_id TEXT, producto_resultante_id INTEGER, cantidad_generada REAL, unidad TEXT, rendimiento_aplicado REAL, tipo TEXT);
        CREATE TABLE IF NOT EXISTS inventory_stock (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, quantity REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(product_id, branch_id));
        CREATE TABLE IF NOT EXISTS production_cost_ledger (id TEXT PRIMARY KEY, batch_id TEXT, output_id TEXT, product_id TEXT, weight REAL, pct_utilizable REAL, cost_total REAL, cost_per_kg REAL, is_waste INTEGER DEFAULT 0);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia_id INTEGER, referencia_tipo TEXT, usuario TEXT, sucursal_id INTEGER, fecha TEXT);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id));
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO productos VALUES (1,'Base','kg',100,0),(2,'Out','kg',0,0);
        INSERT INTO product_recipes VALUES (1,1,'SUBPRODUCTO','R','kg',1,1);
        INSERT INTO product_recipe_components VALUES (1,1,2,80,20,1,'kg',0,2);
        INSERT INTO configuraciones VALUES ('production_waste_mode','separate');
        """
    )
    class _Bus:
        def handler_count(self, _): return 0
        def publish(self, *_a, **_k): return None
    class _Inv:
        def __init__(self, *a, **k): ...
        def get_stock(self, _): return 999
        def process_movement(self, **kwargs): return None
    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())
    monkeypatch.setattr("core.services.recipe_engine.InventoryEngine", _Inv)
    RecipeEngine(db, 1).ejecutar_produccion(1, 1.0, "u")
    waste_rows = db.execute("SELECT COUNT(*) FROM production_cost_ledger WHERE is_waste=1").fetchone()[0]
    assert waste_rows == 1
