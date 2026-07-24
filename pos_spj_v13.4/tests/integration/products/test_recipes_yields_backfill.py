"""PROD-19 pasos 4-5 — backfill recetas/rendimientos legacy → canónico."""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.products_schema import create_products_schema

_recipes = importlib.import_module(
    "migrations.standalone.152_products_recipes_backfill_from_legacy")
_yields = importlib.import_module(
    "migrations.standalone.153_products_yields_backfill_from_legacy")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    # tablas legacy mínimas
    c.execute("CREATE TABLE recetas (id TEXT, nombre TEXT, tipo_receta TEXT, "
              "producto_base_id TEXT, activo INTEGER, rendimiento_esperado_pct REAL)")
    c.execute("CREATE TABLE receta_componentes (id TEXT, receta_id TEXT, producto_id TEXT, "
              "cantidad REAL, unidad TEXT, merma_porcentaje REAL)")
    c.execute("CREATE TABLE product_recipes (id TEXT, product_id TEXT, base_product_id TEXT, "
              "output_product_id TEXT, nombre_receta TEXT, is_active INTEGER, "
              "tipo_receta TEXT, rendimiento_esperado_pct REAL)")
    c.execute("CREATE TABLE product_recipe_components (id TEXT, recipe_id TEXT, "
              "component_product_id TEXT, cantidad REAL, unidad TEXT, merma_pct REAL)")
    c.execute("CREATE TABLE rendimiento_pollo (id TEXT, producto_pollo_id TEXT, "
              "kg_totales REAL)")
    c.execute("CREATE TABLE rendimiento_derivados (id TEXT, producto_pollo_id TEXT, "
              "producto_derivado_id TEXT, porcentaje_rendimiento REAL, es_subproducto INTEGER)")
    c.commit()
    yield c
    c.close()


# ── recetas ──────────────────────────────────────────────────────────────
def test_recetas_backfill_creates_recipe_version_output(conn):
    conn.execute("INSERT INTO recetas VALUES ('r1','Salsa','PROCESSING','prod1',1,95.0)")
    conn.execute("INSERT INTO receta_componentes VALUES ('c1','r1','ing1',2.5,'kg',3.0)")
    _recipes.run(conn)
    rec = conn.execute("SELECT * FROM recipes WHERE id='r1'").fetchone()
    assert rec["product_id"] == "prod1" and rec["active"] == 1
    ver = conn.execute("SELECT * FROM recipe_versions WHERE recipe_id='r1'").fetchone()
    assert ver["version_number"] == 1 and ver["status"] == "ACTIVE"
    comp = conn.execute("SELECT * FROM recipe_components WHERE id='c1'").fetchone()
    assert comp["component_product_id"] == "ing1" and comp["quantity"] == "2.5000"
    assert comp["unit_id"] == "KG" and comp["scrap_pct"] == "3.0000"
    out = conn.execute("SELECT * FROM recipe_outputs WHERE version_id=?",
                       (ver["id"],)).fetchone()
    assert out["product_id"] == "prod1" and out["expected_yield_pct"] == "95.0000"


def test_product_recipes_backfill(conn):
    conn.execute("INSERT INTO product_recipes (id, output_product_id, nombre_receta, "
                 "is_active, tipo_receta) VALUES ('pr1','out1','Corte',1,'CUTTING')")
    conn.execute("INSERT INTO product_recipe_components (id, recipe_id, "
                 "component_product_id, cantidad, unidad, merma_pct) "
                 "VALUES ('pc1','pr1','comp1',1.0,'pza',0)")
    _recipes.run(conn)
    assert conn.execute("SELECT recipe_type FROM recipes WHERE id='pr1'").fetchone()[0] == "CUTTING"
    assert conn.execute("SELECT component_product_id FROM recipe_components WHERE id='pc1'"
                        ).fetchone()[0] == "comp1"


def test_recipes_backfill_idempotent(conn):
    conn.execute("INSERT INTO recetas VALUES ('r1','Salsa','PROCESSING','prod1',1,95.0)")
    conn.execute("INSERT INTO receta_componentes VALUES ('c1','r1','ing1',2.5,'kg',3.0)")
    _recipes.run(conn)
    _recipes.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM recipe_versions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM recipe_components").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM recipe_outputs").fetchone()[0] == 1


def test_inactive_recipe_is_draft(conn):
    conn.execute("INSERT INTO recetas VALUES ('r2','Vieja','PROCESSING','prod2',0,NULL)")
    _recipes.run(conn)
    assert conn.execute("SELECT status FROM recipe_versions WHERE recipe_id='r2'"
                        ).fetchone()[0] == "DRAFT"


# ── rendimientos ───────────────────────────────────────────────────────────
def test_yields_backfill_profile_version_outputs(conn):
    conn.execute("INSERT INTO rendimiento_pollo VALUES ('yp1','pollo1',100.0)")
    conn.execute("INSERT INTO rendimiento_derivados VALUES ('d1','pollo1','pechuga',35.5,0)")
    conn.execute("INSERT INTO rendimiento_derivados VALUES ('d2','pollo1','viscera',5.0,1)")
    _yields.run(conn)
    prof = conn.execute("SELECT * FROM yield_profiles WHERE id='yp1'").fetchone()
    assert prof["input_product_id"] == "pollo1" and prof["active"] == 1
    ver = conn.execute("SELECT * FROM yield_profile_versions WHERE yield_profile_id='yp1'"
                       ).fetchone()
    assert ver["status"] == "ACTIVE"
    outs = {r["product_id"]: r for r in conn.execute(
        "SELECT * FROM yield_outputs WHERE version_id=?", (ver["id"],)).fetchall()}
    assert outs["pechuga"]["expected_yield_pct"] == "35.5000"
    assert outs["pechuga"]["output_type"] == "MAIN" and outs["pechuga"]["unit_id"] == "KG"
    assert outs["viscera"]["output_type"] == "BY_PRODUCT"


def test_yields_backfill_idempotent(conn):
    conn.execute("INSERT INTO rendimiento_pollo VALUES ('yp1','pollo1',100.0)")
    conn.execute("INSERT INTO rendimiento_derivados VALUES ('d1','pollo1','pechuga',35.5,0)")
    _yields.run(conn)
    _yields.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM yield_profiles").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM yield_profile_versions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM yield_outputs").fetchone()[0] == 1


def test_empty_legacy_is_noop(conn):
    _recipes.run(conn)
    _yields.run(conn)
    assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM yield_profiles").fetchone()[0] == 0
