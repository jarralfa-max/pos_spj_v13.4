from __future__ import annotations

import sqlite3

from core.services.recipe_engine import RecipeEngine
from repositories.recetas import RecetaRepository


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg', precio_compra REAL DEFAULT 0, activo INTEGER DEFAULT 1, is_active INTEGER DEFAULT 1, tipo_producto TEXT DEFAULT 'simple', costo REAL DEFAULT 0);
        CREATE TABLE product_recipes (id TEXT PRIMARY KEY, nombre_receta TEXT, product_id TEXT, tipo_receta TEXT, unidad_base TEXT DEFAULT 'kg', peso_promedio_kg REAL DEFAULT 1, is_active INTEGER DEFAULT 1, activa INTEGER DEFAULT 1, piece_product_id TEXT, validates_at TEXT, created_at TEXT, total_rendimiento REAL DEFAULT 0, total_merma REAL DEFAULT 0);
        CREATE TABLE product_recipe_components (id TEXT PRIMARY KEY, recipe_id TEXT, component_product_id TEXT, rendimiento_pct REAL DEFAULT 0, merma_pct REAL DEFAULT 0, cantidad REAL DEFAULT 0, unidad TEXT DEFAULT 'kg', component_role TEXT DEFAULT '', factor_costo REAL DEFAULT 1.0, tolerancia_pct REAL DEFAULT 2.0, orden INTEGER DEFAULT 0, descripcion TEXT DEFAULT '');
        CREATE TABLE recipe_dependency_graph (parent_recipe_id TEXT, child_product_id TEXT, depth INTEGER DEFAULT 1, PRIMARY KEY (parent_recipe_id, child_product_id));
        CREATE TABLE producciones (id TEXT PRIMARY KEY, receta_id INTEGER, producto_base_id INTEGER, cantidad_base REAL, unidad_base TEXT, usuario TEXT, sucursal_id INTEGER, notas TEXT, estado TEXT, fecha TEXT, operation_id TEXT UNIQUE);
        CREATE TABLE produccion_detalle (id TEXT PRIMARY KEY, produccion_id TEXT, producto_resultante_id INTEGER, cantidad_generada REAL, unidad TEXT, rendimiento_aplicado REAL, tipo TEXT);
        CREATE TABLE IF NOT EXISTS inventory_stock (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, quantity REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(product_id, branch_id));
        CREATE TABLE IF NOT EXISTS production_cost_ledger (id TEXT PRIMARY KEY, batch_id TEXT, output_id TEXT, product_id TEXT, weight REAL, pct_utilizable REAL, cost_total REAL, cost_per_kg REAL, is_waste INTEGER DEFAULT 0);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia_id INTEGER, referencia_tipo TEXT, usuario TEXT, sucursal_id INTEGER, fecha TEXT);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id));
        """
    )
    return c


def test_repository_persists_component_quantity_fields():
    conn = _db()
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (1,'Combo','compuesto'),(2,'Pechuga','simple')")
    repo = RecetaRepository(conn)
    rid = repo.create("R", 1, [{
        "component_product_id": 2, "cantidad": 1.25, "unidad": "kg",
        "component_role": "input", "factor_costo": 0.8, "orden": 0
    }], "u", "COMBINACION")
    comp = repo.get_components(rid)[0]
    assert comp["cantidad"] == 1.25
    assert comp["unidad"] == "kg"
    assert comp["component_role"] == "input"
    assert abs(comp["factor_costo"] - 0.8) < 1e-9


def test_engine_combinacion_uses_real_quantities(monkeypatch):
    conn = _db()
    conn.execute("INSERT INTO productos(id,nombre,unidad,precio_compra,tipo_producto) VALUES (1,'Combo','kg',0,'compuesto'),(2,'Pechuga','kg',0,'simple'),(3,'Pierna','kg',0,'simple'),(4,'Ala','kg',0,'simple')")
    conn.execute("INSERT INTO product_recipes(id,nombre_receta,product_id,tipo_receta,unidad_base,peso_promedio_kg,is_active) VALUES (1,'Combo 2.5kg',1,'COMBINACION','kg',1,1)")
    conn.execute("INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,unidad,orden) VALUES (1,2,1.0,'kg',0),(1,3,1.0,'kg',1),(1,4,0.5,'kg',2)")
    conn.commit()

    class _Inv:
        def __init__(self, *a, **k): ...
        def get_stock(self, _): return 9999
        def process_movement(self, **kwargs): return None
    class _Bus:
        def handler_count(self, _): return 0
        def publish(self, *_a, **_k): return None
    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())

    dto = RecipeEngine(conn, 1).ejecutar_produccion(1, 1.0, "qa")
    outs = [c for c in dto.componentes if c.tipo == "salida"]
    qtys = sorted([round(c.cantidad, 3) for c in outs])
    assert qtys == [0.5, 1.0, 1.0]


def test_engine_subproducto_still_uses_percentages():
    conn = _db()
    eng = RecipeEngine(conn, 1)
    movs = eng._calcular_movimientos(
        "SUBPRODUCTO", {"unidad_base": "kg"},
        [{"producto_id": 2, "prod_nombre": "Pechuga", "rendimiento_pct": 70, "merma_pct": 30, "unidad": "kg"}],
        cantidad_base=1.0, peso_prom=1.0, prod_base_id=1, prod_base_nombre="Pollo"
    )
    assert any(m["movement_type"] == "PRODUCCION_ENTRADA" and abs(m["delta"] - 0.7) < 1e-6 for m in movs)
