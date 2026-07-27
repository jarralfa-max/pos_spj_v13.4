"""ProductRecipeQueryService — read side de recetas (capa de aplicación). Read-only.

Sirve las recetas de un producto, sus versiones y el detalle (componentes/outputs)
de una versión para la pantalla de gestión.
"""

from __future__ import annotations


class ProductRecipeQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_recipes(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, recipe_type, name, active FROM recipes WHERE product_id=? "
            "ORDER BY name", (product_id,)).fetchall()
        return [dict(r) for r in rows]

    def list_versions(self, recipe_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, version_number, status, approved_by_user_id, created_by "
            "FROM recipe_versions WHERE recipe_id=? ORDER BY version_number DESC",
            (recipe_id,)).fetchall()
        return [dict(r) for r in rows]

    def version_detail(self, version_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, recipe_id, version_number, status, created_by "
            "FROM recipe_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        detail = dict(row)
        detail["components"] = [dict(r) for r in self._conn.execute(
            "SELECT id, component_product_id, quantity, unit_id, scrap_pct, sequence "
            "FROM recipe_components WHERE version_id=? ORDER BY sequence",
            (version_id,)).fetchall()]
        detail["outputs"] = [dict(r) for r in self._conn.execute(
            "SELECT id, product_id, output_type, quantity, unit_id, "
            "expected_yield_pct, sequence FROM recipe_outputs WHERE version_id=? "
            "ORDER BY sequence", (version_id,)).fetchall()]
        return detail
