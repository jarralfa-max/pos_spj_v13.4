# core/services/recipes/recipe_resolver.py — FASE 4
"""
RecipeResolver — BOM explosion for sales and production planning.

Rules by tipo_producto:
  compuesto  (COMBINACION) — sells from component stock (virtual product).
                             BOM explosion: deduct components, not the product itself.
  procesable (SUBPRODUCTO) — sells from own stock. Production consumes base ingredient.
  producido  (PRODUCCION)  — sells from own stock. Production consumes input ingredients.
  simple / insumo          — sells from own stock. No recipe expansion.

The resolver is read-only — it never writes to the DB.
Inventory deduction / production recording is delegated to the handlers that
listen to SALE_ITEMS_PROCESS / PRODUCTION_ITEMS_PROCESS via the EventBus.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger("spj.services.recipes.resolver")


# ── Value objects ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeductionLine:
    """A single inventory movement produced by BOM explosion."""
    product_id:     int
    product_nombre: str
    quantity:       float
    is_virtual:     bool = False   # True when parent was a virtual compuesto product


@dataclass
class BOMExplosion:
    """
    Result of resolve_for_sale().

    deductions: flat list of inventory lines to deduct.
                For direct products: one line with the product itself.
                For virtual compuesto products: lines for each component (recursive).
    is_virtual: True when root product has no own stock — sell by deducting components.
    cycle_detected: True when a cycle was found and expansion was truncated.
    """
    root_product_id: int
    requested_qty:   float
    is_virtual:      bool
    deductions:      List[DeductionLine] = field(default_factory=list)
    cycle_detected:  bool = False


@dataclass
class ProductionLine:
    """An input to consume or output to produce in a production run."""
    product_id:     int
    product_nombre: str
    quantity:       float
    movement_type:  str   # "CONSUME" | "PRODUCE" | "WASTE"


@dataclass
class ProductionPlan:
    """
    Result of resolve_for_production().

    inputs:  what the production will consume from stock.
    outputs: what the production will add to stock.
    """
    base_product_id:     int
    base_product_nombre: str
    recipe_id:           int
    recipe_type:         str
    requested_qty:       float
    inputs:              List[ProductionLine] = field(default_factory=list)
    outputs:             List[ProductionLine] = field(default_factory=list)


class BOMCycleError(Exception):
    """Raised when a cycle is detected in the BOM graph."""


# ── Resolver ──────────────────────────────────────────────────────────────────

class RecipeResolver:
    """
    Stateless BOM resolver. Instantiate once per request.

    Usage::

        resolver = RecipeResolver(db)
        explosion = resolver.resolve_for_sale(product_id=5, qty=2.5, branch_id=1)
        for line in explosion.deductions:
            print(f"  deduct {line.quantity:.3f} kg of {line.product_nombre}")

        avail = resolver.virtual_availability(product_id=5, branch_id=1)
    """

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ── Public API ────────────────────────────────────────────────────────────

    def resolve_for_sale(
        self,
        product_id: int,
        qty: float,
        branch_id: int,
    ) -> BOMExplosion:
        """
        Return the inventory deductions needed to fulfil a sale of `qty` units.

        For compuesto products: recursively expand the BOM — the product itself
        has no stock; its components are deducted.
        For all other types: direct deduction from the product's own stock.

        cycle_detected is set True if a cycle was found; expansion is truncated
        at the cycle boundary (no infinite recursion).
        """
        tipo = self._get_tipo_producto(product_id)
        cycle_detected = False
        is_virtual = tipo == "compuesto"

        try:
            deductions = self._expand_bom_for_sale(product_id, qty, visiting=frozenset())
        except BOMCycleError:
            cycle_detected = True
            nombre = self._get_product_nombre(product_id)
            deductions = [DeductionLine(product_id, nombre, qty, is_virtual=False)]
            logger.error("BOM cycle detected at product_id=%s, falling back to direct deduction", product_id)

        return BOMExplosion(
            root_product_id=product_id,
            requested_qty=qty,
            is_virtual=is_virtual,
            deductions=deductions,
            cycle_detected=cycle_detected,
        )

    def resolve_for_production(
        self,
        recipe_id: int,
        qty: float,
    ) -> ProductionPlan:
        """
        Return the inputs and outputs for a production run of `qty` units
        using the specified recipe.

        Does not execute anything — purely a planning/preview function.
        Raises ValueError if the recipe doesn't exist or has no components.
        """
        receta = self._db.execute(
            "SELECT * FROM product_recipes WHERE id = ? AND is_active = 1",
            (recipe_id,)
        ).fetchone()
        if not receta:
            raise ValueError(f"recipe_id={recipe_id} not found or inactive")

        receta = dict(receta)
        tipo = (receta.get("tipo_receta") or "subproducto").lower()
        base_id = receta.get("product_id") or receta.get("base_product_id")
        peso_prom = float(receta.get("peso_promedio_kg") or 1.0)
        base_nombre = self._get_product_nombre(base_id)

        comps = self._db.execute("""
            SELECT rc.component_product_id AS product_id,
                   p.nombre AS product_nombre,
                   COALESCE(rc.cantidad, 0)          AS cantidad,
                   COALESCE(rc.rendimiento_pct, 0)   AS rendimiento_pct,
                   COALESCE(rc.merma_pct, 0)         AS merma_pct,
                   COALESCE(rc.tolerancia_pct, 2.0)  AS tolerancia_pct
            FROM product_recipe_components rc
            JOIN productos p ON p.id = rc.component_product_id
            WHERE rc.recipe_id = ?
            ORDER BY rc.orden, rc.id
        """, (recipe_id,)).fetchall()
        comps = [dict(c) for c in comps]

        if not comps:
            raise ValueError(f"recipe_id={recipe_id} has no components")

        inputs: List[ProductionLine] = []
        outputs: List[ProductionLine] = []

        if tipo == "subproducto":
            total_kg = qty * peso_prom
            inputs.append(ProductionLine(
                product_id=base_id,
                product_nombre=base_nombre,
                quantity=round(total_kg, 4),
                movement_type="CONSUME",
            ))
            for c in comps:
                rend = float(c.get("rendimiento_pct") or 0)
                if rend > 0:
                    kg_out = round(total_kg * rend / 100, 4)
                    if kg_out > 0:
                        outputs.append(ProductionLine(
                            product_id=c["product_id"],
                            product_nombre=c["product_nombre"],
                            quantity=kg_out,
                            movement_type="PRODUCE",
                        ))
                merma_pct = float(c.get("merma_pct") or 0)
                if merma_pct > 0:
                    kg_merma = round(total_kg * merma_pct / 100, 4)
                    if kg_merma > 0:
                        outputs.append(ProductionLine(
                            product_id=c["product_id"],
                            product_nombre=c["product_nombre"],
                            quantity=kg_merma,
                            movement_type="WASTE",
                        ))

        elif tipo in ("combinacion", "produccion"):
            # Components are consumed; base product is produced
            for c in comps:
                cant = float(c.get("cantidad") or 0)
                if cant <= 0:
                    # Fallback: use rendimiento_pct / 100 as fraction
                    rend_pct = float(c.get("rendimiento_pct") or 0)
                    cant = rend_pct / 100.0
                if cant <= 0:
                    continue
                total_comp = round(cant * qty, 4)
                inputs.append(ProductionLine(
                    product_id=c["product_id"],
                    product_nombre=c["product_nombre"],
                    quantity=total_comp,
                    movement_type="CONSUME",
                ))
                merma_pct = float(c.get("merma_pct") or 0)
                if merma_pct > 0:
                    kg_merma = round(total_comp * merma_pct / 100, 4)
                    if kg_merma > 0:
                        inputs.append(ProductionLine(
                            product_id=c["product_id"],
                            product_nombre=c["product_nombre"],
                            quantity=kg_merma,
                            movement_type="WASTE",
                        ))
            outputs.append(ProductionLine(
                product_id=base_id,
                product_nombre=base_nombre,
                quantity=round(qty, 4),
                movement_type="PRODUCE",
            ))

        return ProductionPlan(
            base_product_id=base_id,
            base_product_nombre=base_nombre,
            recipe_id=recipe_id,
            recipe_type=tipo,
            requested_qty=qty,
            inputs=inputs,
            outputs=outputs,
        )

    def virtual_availability(self, product_id: int, branch_id: int) -> float:
        """
        For compuesto products: maximum quantity that can be assembled from
        available component stock.

        For all other types: return the product's own stock at the branch.

        Returns 0.0 if any required component has zero stock or no recipe exists.
        """
        tipo = self._get_tipo_producto(product_id)
        if tipo != "compuesto":
            return self._get_stock(product_id, branch_id)

        recipe = self._db.execute(f"""
            SELECT id FROM product_recipes
            WHERE {self._product_col()} = ? AND is_active = 1 LIMIT 1
        """, (product_id,)).fetchone()

        if not recipe:
            return 0.0

        comps = self._db.execute("""
            SELECT rc.component_product_id AS product_id,
                   COALESCE(rc.cantidad, 0)        AS cantidad,
                   COALESCE(rc.rendimiento_pct, 0) AS rendimiento_pct
            FROM product_recipe_components rc
            WHERE rc.recipe_id = ?
            ORDER BY rc.orden, rc.id
        """, (recipe[0],)).fetchall()

        min_available = float("inf")
        for c in comps:
            c = dict(c)
            cant = float(c.get("cantidad") or 0)
            if cant <= 0:
                cant = float(c.get("rendimiento_pct") or 0) / 100.0
            if cant <= 0:
                continue
            stock = self._get_stock(c["product_id"], branch_id)
            available = stock / cant
            if available < min_available:
                min_available = available

        return round(min_available, 4) if min_available != float("inf") else 0.0

    def check_cycle(self, product_id: int) -> bool:
        """
        Return True if a BOM cycle is detected starting from product_id.
        Does not raise — safe to call in validation contexts.
        """
        try:
            self._expand_bom_for_sale(product_id, 1.0, visiting=frozenset())
            return False
        except BOMCycleError:
            return True

    # ── Internal BOM expansion ────────────────────────────────────────────────

    def _expand_bom_for_sale(
        self,
        product_id: int,
        qty: float,
        visiting: frozenset,
    ) -> List[DeductionLine]:
        """
        Recursively expand product_id into leaf-level DeductionLines.

        visiting is a frozenset of product_ids on the current recursion path
        (immutable — each recursive call gets its own copy so diamond
        dependencies are allowed; only true cycles are rejected).
        """
        if product_id in visiting:
            raise BOMCycleError(f"BOM cycle at product_id={product_id}")

        tipo = self._get_tipo_producto(product_id)

        if tipo != "compuesto":
            nombre = self._get_product_nombre(product_id)
            return [DeductionLine(product_id, nombre, round(qty, 6), is_virtual=False)]

        # Compuesto — expand into components
        recipe_row = self._db.execute(f"""
            SELECT id FROM product_recipes
            WHERE {self._product_col()} = ? AND is_active = 1 LIMIT 1
        """, (product_id,)).fetchone()

        if not recipe_row:
            # No recipe despite being compuesto — fall back to direct deduction
            nombre = self._get_product_nombre(product_id)
            logger.warning("product_id=%s is compuesto but has no active recipe — direct deduction", product_id)
            return [DeductionLine(product_id, nombre, round(qty, 6), is_virtual=True)]

        recipe_id = recipe_row[0]
        comps = self._db.execute("""
            SELECT rc.component_product_id AS product_id,
                   p.nombre               AS product_nombre,
                   COALESCE(rc.cantidad, 0)        AS cantidad,
                   COALESCE(rc.rendimiento_pct, 0) AS rendimiento_pct
            FROM product_recipe_components rc
            JOIN productos p ON p.id = rc.component_product_id
            WHERE rc.recipe_id = ?
            ORDER BY rc.orden, rc.id
        """, (recipe_id,)).fetchall()

        child_visiting = visiting | {product_id}
        result: List[DeductionLine] = []

        for c in comps:
            c = dict(c)
            cant = float(c.get("cantidad") or 0)
            if cant <= 0:
                cant = float(c.get("rendimiento_pct") or 0) / 100.0
            if cant <= 0:
                continue
            comp_qty = round(qty * cant, 6)
            # Recurse — child may also be compuesto
            child_lines = self._expand_bom_for_sale(c["product_id"], comp_qty, child_visiting)
            result.extend(child_lines)

        return result

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _get_tipo_producto(self, product_id: int) -> str:
        row = self._db.execute(
            "SELECT tipo_producto FROM productos WHERE id = ?", (product_id,)
        ).fetchone()
        if not row:
            return "simple"
        val = row[0] if not hasattr(row, "keys") else row["tipo_producto"]
        return (val or "simple").lower()

    def _get_product_nombre(self, product_id: int) -> str:
        row = self._db.execute(
            "SELECT nombre FROM productos WHERE id = ?", (product_id,)
        ).fetchone()
        if not row:
            return f"#product_{product_id}"
        return row[0] if not hasattr(row, "keys") else row["nombre"]

    def _get_stock(self, product_id: int, branch_id: int) -> float:
        try:
            row = self._db.execute(
                """SELECT COALESCE(quantity, 0)
                   FROM inventory_stock
                   WHERE product_id = ? AND branch_id = ?""",
                (product_id, branch_id),
            ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception as exc:
            logger.error(
                "inventory_stock no disponible para resolver receta; product_id=%s branch_id=%s: %s",
                product_id, branch_id, exc,
            )
            return 0.0

    def _product_col(self) -> str:
        """Return the column name for the product FK on product_recipes."""
        try:
            cols = {r[1] for r in self._db.execute(
                "PRAGMA table_info(product_recipes)"
            ).fetchall()}
            return "product_id" if "product_id" in cols else "base_product_id"
        except Exception:
            return "product_id"
