"""La venta de un combo (compuesto) descuenta componentes, no el producto virtual."""
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


def test_combo_bom_explosion_deducts_components():
    conn = make_db()
    branch = new_uuid()
    combo = _producto(conn, "Combo Parrilla", tipo="compuesto")
    carne = _producto(conn, "Arrachera")
    chorizo = _producto(conn, "Chorizo")

    RecipeService(conn).create_recipe(
        "Parrilla", combo,
        [
            {"component_product_id": carne, "cantidad": 1.5},
            {"component_product_id": chorizo, "cantidad": 0.5},
        ],
        usuario="tester", tipo_receta="COMBINACION",
    )

    resolver = RecipeResolver(conn)
    explosion = resolver.resolve_for_sale(combo, qty=2.0, branch_id=branch)

    assert explosion.is_virtual is True
    assert explosion.cycle_detected is False
    lines = {l.product_id: l.quantity for l in explosion.deductions}
    # El combo NO se descuenta a sí mismo — solo componentes escalados x2
    assert combo not in lines
    assert lines[carne] == 3.0
    assert lines[chorizo] == 1.0


def test_simple_product_deducts_itself():
    conn = make_db()
    simple = _producto(conn, "Costilla")
    resolver = RecipeResolver(conn)
    explosion = resolver.resolve_for_sale(simple, qty=1.0, branch_id=new_uuid())
    assert explosion.is_virtual is False
    assert [(l.product_id, l.quantity) for l in explosion.deductions] == [(simple, 1.0)]
