from __future__ import annotations

import sqlite3

from core.services.recipe_engine import RecipeEngine


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg', precio_compra REAL DEFAULT 0, costo REAL DEFAULT 0, tipo_producto TEXT DEFAULT 'simple');
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, nombre_receta TEXT, unidad_base TEXT DEFAULT 'kg', peso_promedio_kg REAL DEFAULT 1, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, cantidad REAL DEFAULT 0, rendimiento_pct REAL DEFAULT 0, merma_pct REAL DEFAULT 0, factor_costo REAL DEFAULT 1.0, unidad TEXT DEFAULT 'kg', orden INTEGER DEFAULT 0, tolerancia_pct REAL DEFAULT 2.0);
        CREATE TABLE producciones (id TEXT PRIMARY KEY, receta_id INTEGER, producto_base_id INTEGER, cantidad_base REAL, unidad_base TEXT, usuario TEXT, sucursal_id INTEGER, notas TEXT, estado TEXT, fecha TEXT, operation_id TEXT UNIQUE);
        CREATE TABLE produccion_detalle (id TEXT PRIMARY KEY, produccion_id TEXT, producto_resultante_id INTEGER, cantidad_generada REAL, unidad TEXT, rendimiento_aplicado REAL, tipo TEXT);
        CREATE TABLE IF NOT EXISTS inventory_stock (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, quantity REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(product_id, branch_id));
        CREATE TABLE IF NOT EXISTS production_cost_ledger (id TEXT PRIMARY KEY, batch_id TEXT, output_id TEXT, product_id TEXT, weight REAL, pct_utilizable REAL, cost_total REAL, cost_per_kg REAL, is_waste INTEGER DEFAULT 0);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia_id INTEGER, referencia_tipo TEXT, usuario TEXT, sucursal_id INTEGER, fecha TEXT);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id));
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        """
    )
    return c


def test_phase6_costing_allocates_different_cost_per_kg_and_waste(monkeypatch):
    db = _db()
    db.executescript(
        """
        INSERT INTO productos(id,nombre,precio_compra,tipo_producto) VALUES (1,'Pollo Entero',100,'procesable'),(2,'Pechuga',0,'simple'),(3,'Huacal',0,'simple');
        INSERT INTO product_recipes(id,product_id,tipo_receta,nombre_receta,unidad_base,peso_promedio_kg,is_active) VALUES (1,1,'SUBPRODUCTO','Despiece','kg',1,1);
        INSERT INTO product_recipe_components(recipe_id,component_product_id,rendimiento_pct,merma_pct,factor_costo,orden) VALUES (1,2,50,0,1.5,0),(1,3,40,10,0.5,1);
        INSERT INTO configuraciones(clave,valor) VALUES ('production_waste_mode','separate');
        """
    )
    captured = {}
    class _Bus:
        def handler_count(self, _): return 0
        def publish(self, evt, payload, strict=False): captured["payload"] = payload
    class _Inv:
        def __init__(self, *a, **k): ...
        def get_stock(self, _): return 999
        def process_movement(self, **kwargs): return None
    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())
    monkeypatch.setattr("core.services.recipe_engine.InventoryEngine", _Inv)

    RecipeEngine(db, 1).ejecutar_produccion(1, 1.0, "qa")
    p2 = db.execute("SELECT precio_compra,costo FROM productos WHERE id=2").fetchone()
    p3 = db.execute("SELECT precio_compra,costo FROM productos WHERE id=3").fetchone()
    assert p2[0] != p3[0]
    assert p2[1] == p2[0] and p3[1] == p3[0]
    ledger_rows = db.execute("SELECT COUNT(*) FROM production_cost_ledger").fetchone()[0]
    assert ledger_rows >= 2
    costs = captured["payload"]["costs"]
    assert costs["raw_material_cost"] > 0 and costs["finished_goods_cost"] > 0 and costs["waste_cost"] > 0
