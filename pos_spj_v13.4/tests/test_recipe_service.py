"""
tests/test_recipe_service.py — FASE 3 ERP Refactor

Verifica que RecipeService:
  - Delega correctamente a RecetaRepository
  - Expone métodos de consulta y comando con firmas limpias
  - Lanza RecetaError (y subclases) desde RecetaRepository sin wrap
  - get_products_for_ui() devuelve lista con los campos esperados
  - get_recipe_data_for_edit() devuelve (receta, componentes) o (None, [])
"""
from __future__ import annotations

import sqlite3
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.recipes.recipe_service import RecipeService
from repositories.recetas import RecetaError


# ── Fixture: in-memory DB con esquema mínimo ──────────────────────────────────

@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            unidad TEXT DEFAULT 'kg',
            activo INTEGER DEFAULT 1,
            tipo_producto TEXT DEFAULT 'simple',
            es_compuesto INTEGER DEFAULT 0,
            es_subproducto INTEGER DEFAULT 0
        );

        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_receta TEXT NOT NULL,
            product_id INTEGER,
            base_product_id INTEGER,
            tipo_receta TEXT DEFAULT 'SUBPRODUCTO',
            total_rendimiento REAL DEFAULT 0,
            total_merma REAL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            activa INTEGER DEFAULT 1,
            piece_product_id INTEGER,
            validates_at TEXT,
            created_at TEXT
        );

        CREATE TABLE product_recipe_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            component_product_id INTEGER NOT NULL,
            rendimiento_pct REAL DEFAULT 0,
            merma_pct REAL DEFAULT 0,
            tolerancia_pct REAL DEFAULT 2.0,
            orden INTEGER DEFAULT 0,
            descripcion TEXT DEFAULT ''
        );

        CREATE TABLE recipe_dependency_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_recipe_id INTEGER,
            child_product_id INTEGER,
            depth INTEGER DEFAULT 1
        );
    """)

    # Seed products
    conn.execute(
        "INSERT INTO productos (nombre, tipo_producto) VALUES (?, ?)",
        ("Pollo Entero", "procesable"),
    )
    conn.execute(
        "INSERT INTO productos (nombre, tipo_producto) VALUES (?, ?)",
        ("Pechuga", "simple"),
    )
    conn.execute(
        "INSERT INTO productos (nombre, tipo_producto) VALUES (?, ?)",
        ("Pierna", "simple"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def svc(db):
    return RecipeService(db)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _componentes_validos():
    # sum(rendimiento_pct) must equal 100 — repo rule
    return [
        {"component_product_id": 2, "rendimiento_pct": 60.0, "merma_pct": 0.0,
         "descripcion": "pechuga", "orden": 0},
        {"component_product_id": 3, "rendimiento_pct": 40.0, "merma_pct": 0.0,
         "descripcion": "pierna",  "orden": 1},
    ]


# ── get_products_for_ui ───────────────────────────────────────────────────────

class TestGetProductsForUi:

    def test_retorna_lista_de_dicts(self, svc):
        prods = svc.get_products_for_ui()
        assert isinstance(prods, list)
        assert len(prods) == 3

    def test_cada_item_tiene_campos_requeridos(self, svc):
        for p in svc.get_products_for_ui():
            assert "id"     in p
            assert "nombre" in p
            assert "unidad" in p

    def test_unidad_nunca_es_none(self, svc, db):
        db.execute("INSERT INTO productos (nombre, unidad, activo) VALUES ('X', NULL, 1)")
        db.commit()
        prods = svc.get_products_for_ui()
        for p in prods:
            assert p["unidad"] is not None

    def test_solo_activos(self, svc, db):
        db.execute("INSERT INTO productos (nombre, activo) VALUES ('Inactivo', 0)")
        db.commit()
        prods = svc.get_products_for_ui()
        nombres = [p["nombre"] for p in prods]
        assert "Inactivo" not in nombres


# ── create_recipe ─────────────────────────────────────────────────────────────

class TestCreateRecipe:

    def test_crea_receta_y_retorna_id(self, svc):
        rid = svc.create_recipe(
            nombre="Despiece Pollo",
            base_product_id=1,
            components=_componentes_validos(),
            usuario="test",
            tipo_receta="SUBPRODUCTO",
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_receta_aparece_en_get_all(self, svc):
        svc.create_recipe("Despiece", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        recipes = svc.get_all_recipes()
        assert any(r["nombre_receta"] == "Despiece" for r in recipes)

    def test_tipo_receta_incorrecto_lanza_error(self, svc):
        """SUBPRODUCTO requiere tipo_producto='procesable'; producto 2 es 'simple'."""
        with pytest.raises(RecetaError):
            svc.create_recipe(
                nombre="Mala Receta",
                base_product_id=2,           # tipo_producto='simple', no 'procesable'
                components=[
                    {"component_product_id": 3, "rendimiento_pct": 100.0,
                     "merma_pct": 0.0, "orden": 0, "descripcion": ""},
                ],
                usuario="u",
                tipo_receta="SUBPRODUCTO",   # requiere 'procesable' — error esperado
            )

    def test_default_tipo_receta_es_subproducto(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u")
        r = svc.get_recipe_by_id(rid)
        assert (r.get("tipo_receta") or "SUBPRODUCTO").upper() == "SUBPRODUCTO"

    def test_receta_duplicada_lanza_error(self, svc):
        from repositories.recetas import RecetaDuplicadaError
        svc.create_recipe("R1", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        with pytest.raises((RecetaDuplicadaError, RecetaError)):
            svc.create_recipe("R2", 1, _componentes_validos(), "u", "SUBPRODUCTO")


# ── get_recipe_by_id ──────────────────────────────────────────────────────────

class TestGetRecipeById:

    def test_retorna_dict_correcto(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        r = svc.get_recipe_by_id(rid)
        assert r is not None
        assert r["id"] == rid
        assert r["nombre_receta"] == "R"

    def test_retorna_none_para_id_inexistente(self, svc):
        assert svc.get_recipe_by_id(9999) is None


# ── get_recipe_components ─────────────────────────────────────────────────────

class TestGetRecipeComponents:

    def test_retorna_componentes(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        comps = svc.get_recipe_components(rid)
        assert len(comps) == 2
        ids = {c["component_product_id"] for c in comps}
        assert ids == {2, 3}

    def test_lista_vacia_para_receta_inexistente(self, svc):
        comps = svc.get_recipe_components(9999)
        assert comps == []


# ── get_recipe_for_product ───────────────────────────────────────────────────

class TestGetRecipeForProduct:

    def test_retorna_receta_activa(self, svc):
        svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        r = svc.get_recipe_for_product(1)
        assert r is not None

    def test_retorna_none_si_no_existe(self, svc):
        assert svc.get_recipe_for_product(999) is None


# ── get_recipe_data_for_edit ─────────────────────────────────────────────────

class TestGetRecipeDataForEdit:

    def test_retorna_receta_y_componentes(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        receta, comps = svc.get_recipe_data_for_edit(rid)
        assert receta is not None
        assert receta["id"] == rid
        assert len(comps) == 2

    def test_retorna_none_vacio_para_id_inexistente(self, svc):
        receta, comps = svc.get_recipe_data_for_edit(9999)
        assert receta is None
        assert comps == []


# ── update_recipe ─────────────────────────────────────────────────────────────

class TestUpdateRecipe:

    def test_actualiza_nombre(self, svc):
        rid = svc.create_recipe("Original", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        svc.update_recipe(rid, "Actualizado", _componentes_validos(), "u")
        r = svc.get_recipe_by_id(rid)
        assert r["nombre_receta"] == "Actualizado"

    def test_actualiza_componentes(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        # Only one component: rendimiento must still be 100
        nuevos = [
            {"component_product_id": 2, "rendimiento_pct": 100.0,
             "merma_pct": 0.0, "descripcion": "", "orden": 0},
        ]
        svc.update_recipe(rid, "R", nuevos, "u")
        comps = svc.get_recipe_components(rid)
        assert len(comps) == 1


# ── deactivate_recipe ─────────────────────────────────────────────────────────

class TestDeactivateRecipe:

    def test_desactiva_receta(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        svc.deactivate_recipe(rid, "u")
        # get_all_recipes with default include_inactive=False should not return it
        activas = svc.get_all_recipes(include_inactive=False)
        ids = [r["id"] for r in activas]
        assert rid not in ids

    def test_inactiva_visible_con_include_inactive(self, svc):
        rid = svc.create_recipe("R", 1, _componentes_validos(), "u", "SUBPRODUCTO")
        svc.deactivate_recipe(rid, "u")
        todas = svc.get_all_recipes(include_inactive=True)
        ids = [r["id"] for r in todas]
        assert rid in ids
