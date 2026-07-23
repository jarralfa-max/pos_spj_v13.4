"""RecipeRepository — persistence for recipes, versions, components, outputs (PROD-9).

Decimal ↔ str; loads a version with its components/outputs. Never commits (the
caller owns the transaction). Also exposes a component resolver over ACTIVE
versions for cycle detection.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.products.entities.recipe import Recipe
from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.recipe_enums import (
    OutputType,
    RecipeType,
    RecipeVersionStatus,
)


class RecipeRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── recipe ────────────────────────────────────────────────────────────
    def save_recipe(self, recipe: Recipe) -> None:
        self._conn.execute(
            """INSERT INTO recipes (id, product_id, recipe_type, name, active)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, active=excluded.active""",
            (recipe.id, recipe.product_id, recipe.recipe_type.value, recipe.name,
             int(recipe.active)))

    def get_recipe(self, recipe_id: str) -> Recipe | None:
        row = self._conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if row is None:
            return None
        return Recipe(id=row["id"], product_id=row["product_id"],
                      recipe_type=RecipeType(row["recipe_type"]), name=row["name"],
                      active=bool(row["active"]))

    # ── version + lines ───────────────────────────────────────────────────
    def save_version(self, version: RecipeVersion) -> None:
        self._conn.execute(
            """INSERT INTO recipe_versions
               (id, recipe_id, version_number, status, effective_from, effective_to,
                approved_by_user_id, reason)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, effective_from=excluded.effective_from,
                 effective_to=excluded.effective_to,
                 approved_by_user_id=excluded.approved_by_user_id, reason=excluded.reason""",
            (version.id, version.recipe_id, version.version_number, version.status.value,
             version.effective_from, version.effective_to,
             version.approved_by_user_id, version.reason))
        self._conn.execute("DELETE FROM recipe_components WHERE version_id=?", (version.id,))
        self._conn.execute("DELETE FROM recipe_outputs WHERE version_id=?", (version.id,))
        for c in version.components:
            self._conn.execute(
                """INSERT INTO recipe_components
                   (id, version_id, component_product_id, quantity, unit_id, scrap_pct, sequence)
                   VALUES (?,?,?,?,?,?,?)""",
                (c.id, version.id, c.component_product_id, str(c.quantity), c.unit_id,
                 str(c.scrap_pct), c.sequence))
        for o in version.outputs:
            self._conn.execute(
                """INSERT INTO recipe_outputs
                   (id, version_id, product_id, output_type, quantity, unit_id,
                    expected_yield_pct, sequence)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (o.id, version.id, o.product_id, o.output_type.value, str(o.quantity),
                 o.unit_id, None if o.expected_yield_pct is None else str(o.expected_yield_pct),
                 o.sequence))

    def get_version(self, version_id: str) -> RecipeVersion | None:
        row = self._conn.execute(
            "SELECT * FROM recipe_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        version = RecipeVersion(
            id=row["id"], recipe_id=row["recipe_id"],
            version_number=row["version_number"],
            status=RecipeVersionStatus(row["status"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            approved_by_user_id=row["approved_by_user_id"], reason=row["reason"])
        version.components = [
            RecipeComponent(id=r["id"], version_id=r["version_id"],
                            component_product_id=r["component_product_id"],
                            quantity=Decimal(r["quantity"]), unit_id=r["unit_id"],
                            scrap_pct=Decimal(r["scrap_pct"]), sequence=r["sequence"])
            for r in self._conn.execute(
                "SELECT * FROM recipe_components WHERE version_id=? ORDER BY sequence",
                (version_id,)).fetchall()]
        version.outputs = [
            RecipeOutput(id=r["id"], version_id=r["version_id"], product_id=r["product_id"],
                         output_type=OutputType(r["output_type"]),
                         quantity=Decimal(r["quantity"]), unit_id=r["unit_id"],
                         expected_yield_pct=(None if r["expected_yield_pct"] is None
                                             else Decimal(r["expected_yield_pct"])),
                         sequence=r["sequence"])
            for r in self._conn.execute(
                "SELECT * FROM recipe_outputs WHERE version_id=? ORDER BY sequence",
                (version_id,)).fetchall()]
        return version

    def active_version_for_product(self, product_id: str) -> RecipeVersion | None:
        row = self._conn.execute(
            """SELECT rv.id FROM recipe_versions rv
               JOIN recipes r ON r.id = rv.recipe_id
               WHERE r.product_id=? AND rv.status='ACTIVE'
               ORDER BY rv.version_number DESC LIMIT 1""", (product_id,)).fetchone()
        return self.get_version(row["id"]) if row else None

    def component_resolver(self):
        """Resolver for cycle detection over ACTIVE versions."""
        def resolve(product_id: str) -> list[str]:
            version = self.active_version_for_product(product_id)
            return version.component_product_ids() if version else []
        return resolve
