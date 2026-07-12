"""Stock virtual del combo = mínimo armable según stock de componentes."""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.services.recipes.recipe_resolver import RecipeResolver
from core.services.recipes.recipe_service import RecipeService
from tests.integration._born_clean_db import make_db


def _producto(conn, nombre, tipo="simple") -> str:
    pid = new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, tipo_producto) VALUES (?, ?, 1, ?)",
        (pid, nombre, tipo),
    )
    return pid


def _stock(conn, product_id, branch_id, qty):
    conn.execute(
        "INSERT INTO inventory_stock (branch_id, product_id, quantity) VALUES (?, ?, ?)",
        (branch_id, product_id, qty),
    )


def test_virtual_stock_is_limited_by_scarcest_component():
    conn = make_db()
    branch = new_uuid()
    combo = _producto(conn, "Combo Familiar", tipo="compuesto")
    pollo = _producto(conn, "Pollo")
    carbon = _producto(conn, "Carbón")

    RecipeService(conn).create_recipe(
        "Familiar", combo,
        [
            {"component_product_id": pollo, "cantidad": 2.0},   # 2 kg por combo
            {"component_product_id": carbon, "cantidad": 1.0},  # 1 bolsa por combo
        ],
        usuario="tester", tipo_receta="COMBINACION",
    )
    _stock(conn, pollo, branch, 10.0)    # alcanza para 5
    _stock(conn, carbon, branch, 3.0)    # alcanza para 3  ← limitante

    resolver = RecipeResolver(conn)
    assert resolver.virtual_availability(combo, branch) == 3.0


def test_virtual_stock_zero_without_recipe_or_stock():
    conn = make_db()
    branch = new_uuid()
    combo = _producto(conn, "Combo Sin Receta", tipo="compuesto")
    resolver = RecipeResolver(conn)
    assert resolver.virtual_availability(combo, branch) == 0.0
