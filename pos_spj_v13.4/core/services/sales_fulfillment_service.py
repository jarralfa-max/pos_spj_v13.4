from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from core.services.recipes.recipe_resolver import RecipeResolver, BOMCycleError


@dataclass
class FulfillmentLine:
    product_id: int
    qty: float
    mode: str  # DIRECT | COMPOSITE | VIRTUAL_FROM_COMPONENTS
    source_product_id: int
    name: str = ""


class AvailabilityService:
    def __init__(self, db):
        from core.db.connection import wrap
        self.db = wrap(db)
        self.resolver = RecipeResolver(self.db)

    def physical_stock(self, product_id: int, branch_id: int) -> float:
        return self.resolver._get_stock(product_id, branch_id)

    def virtual_stock(self, product_id: int, branch_id: int) -> float:
        return self.resolver.virtual_availability(product_id, branch_id)


class SaleFulfillmentService:
    def __init__(self, db):
        from core.db.connection import wrap
        self.db = wrap(db)
        self.resolver = RecipeResolver(self.db)
        self.avail = AvailabilityService(self.db)

    def resolve_item(self, product_id: int, qty: float, branch_id: int) -> List[FulfillmentLine]:
        p = self.db.execute(
            "SELECT tipo_producto, COALESCE(es_compuesto,0) AS es_compuesto, COALESCE(es_subproducto,0) AS es_subproducto, nombre FROM productos WHERE id=?",
            (product_id,)
        ).fetchone()
        if not p:
            raise ValueError(f"PRODUCTO_NO_ENCONTRADO: {product_id}")
        tipo = (p["tipo_producto"] if hasattr(p, "keys") else p[0] or "simple").lower()
        name = p["nombre"] if hasattr(p, "keys") else p[3]

        if tipo == "compuesto":
            exp = self.resolver.resolve_for_sale(product_id, qty, branch_id)
            if exp.cycle_detected:
                raise ValueError(f"RECETA_CICLICA: producto={product_id}")
            merged: Dict[int, float] = {}
            for d in exp.deductions:
                merged[d.product_id] = merged.get(d.product_id, 0.0) + d.quantity
            return [FulfillmentLine(pid, q, "COMPOSITE", product_id, name) for pid, q in merged.items() if q > 0]

        physical = self.avail.physical_stock(product_id, branch_id)
        if physical >= qty:
            return [FulfillmentLine(product_id, qty, "DIRECT", product_id, name)]

        can_virtual = tipo == "procesable" or bool((p["es_subproducto"] if hasattr(p, "keys") else p[2]))
        if can_virtual:
            virt = self._virtual_from_recipe_availability(product_id, branch_id)
            if virt >= qty:
                merged = self._virtual_from_recipe_deductions(product_id, qty, branch_id)
                return [FulfillmentLine(pid, q, "VIRTUAL_FROM_COMPONENTS", product_id, name) for pid, q in merged.items() if q > 0]

        missing = max(0.0, qty - physical)
        raise ValueError(f"STOCK_INSUFICIENTE: producto={name} faltante={missing:.3f}")

    def _virtual_from_recipe_deductions(self, product_id: int, qty: float, branch_id: int) -> Dict[int, float]:
        rec = self.db.execute("SELECT id FROM product_recipes WHERE product_id=? AND is_active=1 LIMIT 1", (product_id,)).fetchone()
        if not rec:
            return {}
        comps = self.db.execute("SELECT component_product_id, COALESCE(cantidad,0) cantidad FROM product_recipe_components WHERE recipe_id=?", (rec[0],)).fetchall()
        merged: Dict[int, float] = {}
        for c in comps:
            need = float(c["cantidad"] if hasattr(c, "keys") else c[1]) * qty
            exp = self.resolver.resolve_for_sale(int(c[0]), need, branch_id)
            if exp.cycle_detected:
                raise ValueError(f"RECETA_CICLICA: producto={product_id}")
            for d in exp.deductions:
                merged[d.product_id] = merged.get(d.product_id, 0.0) + d.quantity
        return merged

    def _virtual_from_recipe_availability(self, product_id: int, branch_id: int) -> float:
        rec = self.db.execute("SELECT id FROM product_recipes WHERE product_id=? AND is_active=1 LIMIT 1", (product_id,)).fetchone()
        if not rec:
            return 0.0
        comps = self.db.execute("SELECT component_product_id, COALESCE(cantidad,0) cantidad FROM product_recipe_components WHERE recipe_id=?", (rec[0],)).fetchall()
        if not comps:
            return 0.0
        mins = []
        for c in comps:
            qty = float(c["cantidad"] if hasattr(c, "keys") else c[1])
            if qty <= 0:
                continue
            avail = self.avail.virtual_stock(int(c[0]), branch_id)
            mins.append(avail / qty if qty > 0 else 0.0)
        return min(mins) if mins else 0.0
