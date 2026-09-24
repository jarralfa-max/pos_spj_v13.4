"""Migración 265 — las recetas copiadas por la 152 vuelven a ser legibles.

La 152 escribía `output_type='MAIN'` y copiaba `tipo_receta` legacy tal cual
(`PRODUCCION`, `COMBINACION`, `SUBPRODUCTO`) o `PROCESSING` por omisión: valores
que no existen en los enums del dominio. `RecipeRepository` levantaba
`ValueError` al leer CUALQUIER receta migrada.
"""

import importlib
import sqlite3

import pytest

from backend.domain.products.recipe_enums import OutputType, RecipeType
from backend.infrastructure.db.repositories.products.recipe_repository import RecipeRepository
from backend.infrastructure.db.schema.products_schema import create_products_schema

_152 = importlib.import_module(
    "migrations.standalone.152_products_recipes_backfill_from_legacy")
_265 = importlib.import_module("migrations.standalone.265_repair_backfilled_recipe_types")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("CREATE TABLE product_recipes (id TEXT PRIMARY KEY, base_product_id TEXT,"
              " is_active INT DEFAULT 1, tipo_receta TEXT)")
    c.execute("CREATE TABLE product_recipe_components (id TEXT PRIMARY KEY, recipe_id TEXT,"
              " component_product_id TEXT, cantidad REAL)")
    c.commit()
    yield c
    c.close()


def _legacy(conn, rid, base, tipo):
    conn.execute("INSERT INTO product_recipes VALUES (?,?,1,?)", (rid, base, tipo))
    conn.execute("INSERT INTO product_recipe_components VALUES (?,?,?,2)",
                 (f"{rid}-c", rid, f"{base}-insumo"))
    conn.commit()


def _estado(conn, rid):
    return conn.execute("SELECT status FROM recipe_versions WHERE recipe_id=?",
                        (rid,)).fetchone()[0]


class TestTheDefectIsReal:
    def test_without_265_a_backfilled_recipe_cannot_be_read(self, conn):
        """Fija el defecto para que nadie lo reintroduzca creyendo que la 152
        basta por sí sola."""
        _legacy(conn, "r1", "prod-1", "PRODUCCION")
        _152.run(conn)
        with pytest.raises(ValueError):
            RecipeRepository(conn).active_version_for_product("prod-1")


class TestTheRepair:
    def test_outputs_become_main_product(self, conn):
        _legacy(conn, "r1", "prod-1", "PRODUCCION")
        _152.run(conn)
        _265.run(conn)
        tipos = {r[0] for r in conn.execute("SELECT output_type FROM recipe_outputs")}
        assert tipos == {OutputType.MAIN_PRODUCT.value}

    @pytest.mark.parametrize("legacy,canonico", [
        ("PRODUCCION", RecipeType.PRODUCTION_BOM),
        ("COMBINACION", RecipeType.SALES_EXPLOSION),
        (None, RecipeType.PROCESSING_RECIPE),        # la 152 ponía "PROCESSING"
    ])
    def test_known_legacy_types_are_translated_and_stay_active(self, conn, legacy, canonico):
        _legacy(conn, "r1", "prod-1", legacy)
        _152.run(conn)
        _265.run(conn)
        version = RecipeRepository(conn).active_version_for_product("prod-1")
        assert version is not None
        receta = RecipeRepository(conn).get_recipe("r1")
        assert receta.recipe_type is canonico
        assert [c.component_product_id for c in version.components] == ["prod-1-insumo"]

    def test_subproducto_is_not_guessed_and_goes_to_review(self, conn):
        """Según la 085, el dueño de una receta SUBPRODUCTO es el producto que se
        DESPIEZA; la 152 la copió al revés. Traducirla la pondría a consumir
        inventario según una lectura que nadie verificó."""
        _legacy(conn, "r1", "pollo-entero", "subproducto")
        _152.run(conn)
        _265.run(conn)
        assert RecipeRepository(conn).get_recipe("r1").recipe_type is \
            RecipeType.PROCESSING_RECIPE
        assert _estado(conn, "r1") == "UNDER_REVIEW"
        # No hay versión ACTIVA: no explota al comprar ni al vender.
        assert RecipeRepository(conn).active_version_for_product("pollo-entero") is None

    def test_an_unknown_type_goes_to_review_too(self, conn):
        _legacy(conn, "r1", "prod-1", "COSA_RARA")
        _152.run(conn)
        _265.run(conn)
        assert _estado(conn, "r1") == "UNDER_REVIEW"

    def test_it_is_idempotent_and_does_not_touch_valid_recipes(self, conn):
        _legacy(conn, "r1", "prod-1", "PRODUCCION")
        _152.run(conn)
        conn.execute("INSERT INTO recipes (id, product_id, recipe_type, name, active)"
                     " VALUES ('ok','prod-2','FORMULA','Válida',1)")
        conn.commit()
        _265.run(conn)
        _265.run(conn)
        tipos = dict(conn.execute("SELECT id, recipe_type FROM recipes").fetchall())
        assert tipos == {"r1": "PRODUCTION_BOM", "ok": "FORMULA"}

    def test_an_empty_catalog_is_a_no_op(self, conn):
        _265.run(conn)
        assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0

    def test_without_the_catalog_it_does_nothing(self):
        c = sqlite3.connect(":memory:")
        _265.run(c)
        c.close()
