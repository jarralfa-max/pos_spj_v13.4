"""CRUD de recetas/combos por la ruta canónica RecipeService (UUIDv7)."""
from __future__ import annotations

import uuid as _uuid

from backend.shared.ids import new_uuid
from core.services.recipes.recipe_service import RecipeService
from tests.integration._born_clean_db import make_db


def _producto(conn, nombre, tipo="simple", stock=0.0) -> str:
    pid = new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, tipo_producto, existencia) "
        "VALUES (?, ?, 1, ?, ?)",
        (pid, nombre, tipo, stock),
    )
    return pid


def test_combo_recipe_crud_lifecycle():
    conn = make_db()
    combo = _producto(conn, "Paquete Asado", tipo="compuesto")
    carne = _producto(conn, "Arrachera")
    tortilla = _producto(conn, "Tortillas")

    svc = RecipeService(conn)
    receta_id = svc.create_recipe(
        nombre="Combo Asado",
        base_product_id=combo,
        components=[
            {"component_product_id": carne, "cantidad": 1.5, "unidad": "kg"},
            {"component_product_id": tortilla, "cantidad": 2.0, "unidad": "pza"},
        ],
        usuario="tester",
        tipo_receta="COMBINACION",
    )
    _uuid.UUID(str(receta_id))   # identidad UUIDv7

    receta = svc.get_recipe_by_id(receta_id)
    assert receta is not None

    componentes = svc.get_recipe_components(receta_id)
    assert len(componentes) == 2

    # Update: cambia cantidad de un componente
    svc.update_recipe(
        receta_id,
        nombre="Combo Asado XL",
        components=[
            {"component_product_id": carne, "cantidad": 2.0, "unidad": "kg"},
            {"component_product_id": tortilla, "cantidad": 3.0, "unidad": "pza"},
        ],
        usuario="tester",
    )
    componentes = svc.get_recipe_components(receta_id)
    cantidades = sorted(float(c.get("cantidad") or 0) for c in componentes)
    assert cantidades == [2.0, 3.0]

    # Deactivate (soft-delete)
    svc.deactivate_recipe(receta_id, usuario="tester")
    activa = conn.execute(
        "SELECT is_active FROM product_recipes WHERE id=?", (receta_id,)
    ).fetchone()
    assert activa is not None and activa[0] == 0


def test_recipe_for_product_lookup():
    conn = make_db()
    combo = _producto(conn, "Combo Taquiza", tipo="compuesto")
    comp = _producto(conn, "Pastor")
    svc = RecipeService(conn)
    receta_id = svc.create_recipe(
        "Taquiza", combo,
        [{"component_product_id": comp, "cantidad": 1.0}],
        usuario="tester", tipo_receta="COMBINACION",
    )
    found = svc.get_recipe_for_product(combo)
    assert found is not None
    assert str(found.get("id")) == str(receta_id)
