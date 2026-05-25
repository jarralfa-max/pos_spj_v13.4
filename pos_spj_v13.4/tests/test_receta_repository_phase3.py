from __future__ import annotations

import sqlite3

import pytest

from repositories.recetas import RecetaError, RecetaPercentageError, RecetaRepository


@pytest.fixture()
def repo_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            unidad TEXT DEFAULT 'kg',
            activo INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            tipo_producto TEXT DEFAULT 'simple'
        );
        CREATE TABLE product_recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_receta TEXT,
            product_id INTEGER,
            tipo_receta TEXT DEFAULT 'SUBPRODUCTO',
            total_rendimiento REAL DEFAULT 0,
            total_merma REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            activa INTEGER DEFAULT 1,
            created_at TEXT,
            validates_at TEXT,
            piece_product_id INTEGER
        );
        CREATE TABLE product_recipe_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER,
            component_product_id INTEGER,
            cantidad REAL DEFAULT 0,
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
        """
    )
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (1,'Base Proc','procesable')")
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (2,'Base Comp','compuesto')")
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (3,'Base Prod','producido')")
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (10,'C1','simple')")
    conn.execute("INSERT INTO productos(id,nombre,tipo_producto) VALUES (11,'C2','simple')")
    conn.commit()
    yield conn
    conn.close()


def test_subproducto_exige_total_100(repo_db):
    repo = RecetaRepository(repo_db)
    with pytest.raises(RecetaPercentageError):
        repo.create(
            "R-sub-bad", 1,
            [{"component_product_id": 10, "rendimiento_pct": 70, "merma_pct": 0, "orden": 0}],
            "u", "SUBPRODUCTO"
        )


def test_combinacion_no_exige_100_pero_si_cantidad_positiva(repo_db):
    repo = RecetaRepository(repo_db)
    rid = repo.create(
        "R-combo", 2,
        [
            {"component_product_id": 10, "cantidad": 1.2, "orden": 0},
            {"component_product_id": 11, "cantidad": 0.3, "orden": 1},
        ],
        "u", "COMBINACION"
    )
    assert rid > 0


def test_produccion_no_exige_100(repo_db):
    repo = RecetaRepository(repo_db)
    rid = repo.create(
        "R-prod", 3,
        [{"component_product_id": 10, "cantidad": 2.0, "merma_pct": 5.0, "orden": 0}],
        "u", "PRODUCCION"
    )
    assert rid > 0


def test_update_valida_tipo_producto_vs_tipo_receta(repo_db):
    repo = RecetaRepository(repo_db)
    rid = repo.create(
        "R-sub-ok", 1,
        [{"component_product_id": 10, "rendimiento_pct": 90, "merma_pct": 10, "orden": 0}],
        "u", "SUBPRODUCTO"
    )
    repo_db.execute("UPDATE productos SET tipo_producto='simple' WHERE id=1")
    repo_db.commit()
    with pytest.raises(RecetaError, match="requiere tipo_producto"):
        repo.update(
            rid, "R-sub-upd",
            [{"component_product_id": 10, "rendimiento_pct": 90, "merma_pct": 10, "orden": 0}],
            "u"
        )

