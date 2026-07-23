"""FASE 7 (cárnico) — RecipeEngine production records are UUIDv7-native.

REGLA CERO: ``producciones`` and ``produccion_detalle`` identities must be
UUIDv7 minted with ``new_uuid()`` — never autoincrement + ``last_insert_rowid()``.
Uses the post-cut schema (TEXT id columns) per the mandatory-cut runtime.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from core.services.recipe_engine import RecipeEngine


def _mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (id INTEGER PRIMARY KEY, nombre TEXT, unidad TEXT DEFAULT 'kg', precio_compra REAL DEFAULT 0, costo REAL DEFAULT 0, tipo_producto TEXT DEFAULT 'simple');
        CREATE TABLE product_recipes (id INTEGER PRIMARY KEY, product_id INTEGER, tipo_receta TEXT, nombre_receta TEXT, unidad_base TEXT DEFAULT 'kg', peso_promedio_kg REAL DEFAULT 1, is_active INTEGER DEFAULT 1);
        CREATE TABLE product_recipe_components (id INTEGER PRIMARY KEY, recipe_id INTEGER, component_product_id INTEGER, cantidad REAL DEFAULT 0, rendimiento_pct REAL DEFAULT 0, merma_pct REAL DEFAULT 0, factor_costo REAL DEFAULT 1.0, unidad TEXT DEFAULT 'kg', orden INTEGER DEFAULT 0, tolerancia_pct REAL DEFAULT 2.0);
        -- post-cut identity: TEXT ids (no AUTOINCREMENT)
        CREATE TABLE producciones (id TEXT PRIMARY KEY, receta_id TEXT, producto_base_id TEXT, cantidad_base REAL, unidad_base TEXT, usuario TEXT, sucursal_id TEXT, notas TEXT, estado TEXT, fecha TEXT, operation_id TEXT UNIQUE);
        CREATE TABLE produccion_detalle (id TEXT PRIMARY KEY, produccion_id TEXT, producto_resultante_id TEXT, cantidad_generada REAL, unidad TEXT, rendimiento_aplicado REAL, tipo TEXT);
        CREATE TABLE movimientos_inventario (id TEXT PRIMARY KEY, uuid TEXT UNIQUE, producto_id TEXT, tipo TEXT, tipo_movimiento TEXT, cantidad REAL, descripcion TEXT, referencia_id TEXT, referencia_tipo TEXT, usuario TEXT, sucursal_id TEXT, fecha TEXT);
        CREATE TABLE inventario_actual (id TEXT PRIMARY KEY, producto_id TEXT, sucursal_id TEXT, cantidad REAL DEFAULT 0, costo_promedio REAL DEFAULT 0, UNIQUE(producto_id, sucursal_id));
        CREATE TABLE production_cost_ledger (id TEXT PRIMARY KEY, batch_id TEXT, output_id TEXT, product_id TEXT, weight REAL, pct_utilizable REAL, cost_total REAL, cost_per_kg REAL);
        CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT);
        """
    )
    return conn


@pytest.fixture
def conn(monkeypatch):
    class _Inv:
        def __init__(self, *a, **k): ...
        def get_stock(self, _pid): return 10_000.0
        def process_movement(self, **kwargs): return None

    class _Bus:
        def handler_count(self, _evt): return 0
        def publish(self, *a, **k): return None

    class _Cost:  # focus this test on identity, not cost allocation
        def __init__(self, *a, **k): ...
        def allocate_recipe_run_costs(self, *a, **k):
            return {"raw_material_cost": 0.0, "finished_goods_cost": 0.0, "waste_cost": 0.0}

    monkeypatch.setattr("core.events.event_bus.get_bus", lambda: _Bus())
    monkeypatch.setattr(
        "core.services.finance.production_cost_service.ProductionCostService", _Cost
    )

    c = _mem_db()
    c.execute("INSERT INTO productos(id,nombre,unidad,precio_compra) VALUES (1,'Base','kg',100),(2,'Comp','kg',10)")
    c.execute("INSERT INTO product_recipes(id,product_id,tipo_receta,nombre_receta,unidad_base,peso_promedio_kg,is_active) VALUES (1,1,'SUBPRODUCTO','R','kg',1,1)")
    c.execute("INSERT INTO product_recipe_components(recipe_id,component_product_id,rendimiento_pct,orden) VALUES (1,2,100,1)")
    c.commit()
    return c


def _is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except Exception:
        return False


def test_produccion_id_is_uuid_not_rowid(conn):
    RecipeEngine(conn, branch_id=1).ejecutar_produccion(1, 2.0, "qa")
    rows = conn.execute("SELECT id FROM producciones").fetchall()
    assert len(rows) == 1
    assert _is_uuid(rows[0]["id"]), f"producciones.id no es UUID: {rows[0]['id']!r}"


def test_produccion_detalle_ids_are_uuid_and_fk_resolves(conn):
    RecipeEngine(conn, branch_id=1).ejecutar_produccion(1, 2.0, "qa")
    prod_id = conn.execute("SELECT id FROM producciones").fetchone()["id"]
    dets = conn.execute("SELECT id, produccion_id FROM produccion_detalle").fetchall()
    assert dets, "no produccion_detalle rows"
    for d in dets:
        assert _is_uuid(d["id"]), f"produccion_detalle.id no es UUID: {d['id']!r}"
        assert d["produccion_id"] == prod_id  # FK resolves to the producciones UUID
