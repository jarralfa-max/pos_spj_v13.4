from __future__ import annotations

import sqlite3

import pytest

from core.services.recipe_engine import RecipeEngine, RecipeEngineError


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT, precio_compra REAL DEFAULT 0, costo REAL DEFAULT 0);
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, nombre_receta TEXT, unidad_base TEXT DEFAULT 'kg', peso_promedio_kg REAL DEFAULT 1, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, rendimiento_pct REAL DEFAULT 0, merma_pct REAL DEFAULT 0, cantidad REAL DEFAULT 0, unidad TEXT DEFAULT 'kg', orden INTEGER DEFAULT 0, tolerancia_pct REAL DEFAULT 2.0);
        CREATE TABLE producciones (id TEXT PRIMARY KEY, receta_id INTEGER, producto_base_id INTEGER, cantidad_base REAL, unidad_base TEXT, usuario TEXT, sucursal_id INTEGER, notas TEXT, estado TEXT, fecha TEXT, operation_id TEXT UNIQUE);
        CREATE TABLE produccion_detalle (id TEXT PRIMARY KEY, produccion_id TEXT, producto_resultante_id INTEGER, cantidad_generada REAL, unidad TEXT, rendimiento_aplicado REAL, tipo TEXT);
        CREATE TABLE IF NOT EXISTS inventory_stock (id TEXT PRIMARY KEY, product_id TEXT, branch_id TEXT, quantity REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(product_id, branch_id));
        CREATE TABLE IF NOT EXISTS production_cost_ledger (id TEXT PRIMARY KEY, batch_id TEXT, output_id TEXT, product_id TEXT, weight REAL, pct_utilizable REAL, cost_total REAL, cost_per_kg REAL, is_waste INTEGER DEFAULT 0);
        CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE, producto_id INTEGER, tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia_id INTEGER, referencia_tipo TEXT, usuario TEXT, sucursal_id INTEGER, fecha TEXT);
        CREATE TABLE inventario_actual (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, sucursal_id INTEGER, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id));
        """
    )
    return conn


def _install_mocks(monkeypatch):
    class _Inv:
        def __init__(self, *args, **kwargs): ...
        def get_stock(self, _pid): return 10_000.0
        def process_movement(self, **kwargs): return None

    class _Bus:
        def handler_count(self, _evt): return 0
        def publish(self, *_args, **_kwargs): return None

    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())


@pytest.mark.parametrize(
    "tipo_receta,component_row",
    [
        ("SUBPRODUCTO", "INSERT INTO product_recipe_components(recipe_id,component_product_id,rendimiento_pct,orden) VALUES (1,2,100,1)"),
        ("COMBINACION", "INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,orden) VALUES (1,2,1.5,1)"),
        ("PRODUCCION", "INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,orden) VALUES (1,2,2.0,1)"),
    ],
)
def test_uppercase_recipe_types_generate_movements(tipo_receta, component_row, monkeypatch):
    _install_mocks(monkeypatch)
    conn = _mem_db()
    conn.execute("INSERT INTO productos(id,nombre,unidad,precio_compra) VALUES (1,'Base','kg',100),(2,'Comp','kg',10)")
    conn.execute(
        "INSERT INTO product_recipes(id,product_id,tipo_receta,nombre_receta,unidad_base,peso_promedio_kg,is_active) VALUES (1,1,?,?, 'kg',1,1)",
        (tipo_receta, f"R-{tipo_receta}"),
    )
    conn.execute(component_row)
    conn.commit()

    dto = RecipeEngine(conn, branch_id=1).ejecutar_produccion(1, 2.0, "qa")
    assert dto.total_generado > 0
    assert len(dto.componentes) > 0


def test_invalid_recipe_type_raises_and_does_not_insert_production(monkeypatch):
    _install_mocks(monkeypatch)
    conn = _mem_db()
    conn.execute("INSERT INTO productos(id,nombre,unidad) VALUES (1,'Base','kg'),(2,'Comp','kg')")
    conn.execute(
        "INSERT INTO product_recipes(id,product_id,tipo_receta,nombre_receta,unidad_base,peso_promedio_kg,is_active) VALUES (1,1,'MAGICA','R-Invalida','kg',1,1)"
    )
    conn.execute(
        "INSERT INTO product_recipe_components(recipe_id,component_product_id,cantidad,orden) VALUES (1,2,1,1)"
    )
    conn.commit()

    with pytest.raises(RecipeEngineError, match="TIPO_RECETA_INVALIDO"):
        RecipeEngine(conn, branch_id=1).ejecutar_produccion(1, 1.0, "qa")

    count = conn.execute("SELECT COUNT(*) FROM producciones").fetchone()[0]
    assert count == 0
