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
    unit: str = ""


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

    def _table_columns(self, table: str) -> set[str]:
        try:
            return {str(r[1]) for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            return set()

    def _product_row(self, product_id: int):
        """Read only product columns that exist in the current schema.

        Never reference optional columns inside COALESCE: SQLite raises
        `no such column` before COALESCE can apply. Missing flags are added as
        literal defaults in the SELECT list, which is safe and idempotent.
        """
        cols = self._table_columns("productos")
        select_parts = ["id"]
        select_parts.append("nombre" if "nombre" in cols else "'' AS nombre")
        select_parts.append("unidad" if "unidad" in cols else "'kg' AS unidad")
        select_parts.append("tipo_producto" if "tipo_producto" in cols else "'simple' AS tipo_producto")
        select_parts.append("COALESCE(es_compuesto,0) AS es_compuesto" if "es_compuesto" in cols else "0 AS es_compuesto")
        select_parts.append("COALESCE(es_subproducto,0) AS es_subproducto" if "es_subproducto" in cols else "0 AS es_subproducto")
        return self.db.execute(
            f"SELECT {', '.join(select_parts)} FROM productos WHERE id=? LIMIT 1",
            (str(product_id),),
        ).fetchone()

    def _row_value(self, row, key: str, idx: int, default=None):
        if not row:
            return default
        try:
            if hasattr(row, "keys"):
                return row[key]
        except Exception:
            pass
        try:
            return row[idx]
        except Exception:
            return default

    def _product_name_unit(self, product_id: int) -> tuple[str, str]:
        row = self._product_row(product_id)
        if not row:
            return f"Producto {product_id}", "kg"
        nombre = self._row_value(row, "nombre", 1, f"Producto {product_id}") or f"Producto {product_id}"
        unidad = self._row_value(row, "unidad", 2, "kg") or "kg"
        return str(nombre), str(unidad)

    def _assert_physical_available(self, deductions: Dict[int, float], branch_id: int) -> None:
        """Validate exact physical deductions before SALE_ITEMS_PROCESS.

        This is not a bypass. SaleInventoryHandler still deducts stock and remains
        authoritative. This read-only guard only fails earlier with a clear message
        when the same resolved product lines would fail later in the event bus.
        """
        shortages: list[str] = []
        for pid, qty in deductions.items():
            qty = float(qty or 0)
            if qty <= 0:
                continue
            available = float(self.avail.physical_stock(str(pid), str(branch_id)) or 0)
            if available + 1e-9 < qty:
                nombre, unidad = self._product_name_unit(str(pid))
                shortages.append(f"{nombre}: requiere {qty:.3f} {unidad}, disponible {available:.3f} {unidad}")
        if shortages:
            raise ValueError("STOCK_INSUFICIENTE: " + "; ".join(shortages))

    def resolve_item(self, product_id: int, qty: float, branch_id: int) -> List[FulfillmentLine]:
        p = self._product_row(product_id)
        if not p:
            raise ValueError(f"PRODUCTO_NO_ENCONTRADO: {product_id}")
        tipo = (self._row_value(p, "tipo_producto", 3, "simple") or "simple").lower()
        is_subproducto = bool(self._row_value(p, "es_subproducto", 5, 0))
        name = str(self._row_value(p, "nombre", 1, "") or "")
        unit = str(self._row_value(p, "unidad", 2, "kg") or "kg")

        if tipo == "compuesto":
            exp = self.resolver.resolve_for_sale(product_id, qty, branch_id)
            if exp.cycle_detected:
                raise ValueError(f"RECETA_CICLICA: producto={product_id}")
            merged: Dict[int, float] = {}
            for d in exp.deductions:
                merged[d.product_id] = merged.get(d.product_id, 0.0) + d.quantity
            self._assert_physical_available(merged, branch_id)
            lines: List[FulfillmentLine] = []
            for pid, q in merged.items():
                if q <= 0:
                    continue
                pname, punit = self._product_name_unit(pid)
                lines.append(FulfillmentLine(pid, q, "COMPOSITE", product_id, pname, punit))
            return lines

        physical = self.avail.physical_stock(product_id, branch_id)
        if physical >= qty:
            return [FulfillmentLine(product_id, qty, "DIRECT", product_id, name, unit)]

        can_virtual = tipo == "procesable" or is_subproducto
        if can_virtual:
            virt = self._virtual_from_recipe_availability(product_id, branch_id)
            if virt >= qty:
                merged = self._virtual_from_recipe_deductions(product_id, qty, branch_id)
                self._assert_physical_available(merged, branch_id)
                lines: List[FulfillmentLine] = []
                for pid, q in merged.items():
                    if q <= 0:
                        continue
                    pname, punit = self._product_name_unit(pid)
                    lines.append(FulfillmentLine(pid, q, "VIRTUAL_FROM_COMPONENTS", product_id, pname, punit))
                return lines

        missing = max(0.0, qty - physical)
        raise ValueError(f"STOCK_INSUFICIENTE: producto={name} faltante={missing:.3f} {unit}")

    def _active_recipe_id(self, product_id: int) -> int | None:
        recipe_cols = self._table_columns("product_recipes")
        if not recipe_cols or "id" not in recipe_cols:
            return None
        product_col = "product_id" if "product_id" in recipe_cols else "base_product_id" if "base_product_id" in recipe_cols else ""
        if not product_col:
            return None
        where = f"{product_col}=?"
        if "is_active" in recipe_cols:
            where += " AND is_active=1"
        row = self.db.execute(f"SELECT id FROM product_recipes WHERE {where} LIMIT 1", (str(product_id),)).fetchone()
        if not row:
            return None
        try:
            return int(row["id"] if hasattr(row, "keys") else row[0])
        except Exception:
            return None

    def _recipe_components(self, recipe_id: int) -> list[tuple[int, float]]:
        comp_cols = self._table_columns("product_recipe_components")
        if not comp_cols:
            return []
        product_col = next((c for c in ("component_product_id", "producto_id", "componente_id", "product_id") if c in comp_cols), "")
        qty_col = next((c for c in ("cantidad", "qty", "quantity") if c in comp_cols), "")
        recipe_col = "recipe_id" if "recipe_id" in comp_cols else "receta_id" if "receta_id" in comp_cols else ""
        if not product_col or not qty_col or not recipe_col:
            return []
        rows = self.db.execute(
            f"SELECT {product_col} AS component_product_id, {qty_col} AS cantidad FROM product_recipe_components WHERE {recipe_col}=?",
            (int(recipe_id),),
        ).fetchall()
        comps: list[tuple[int, float]] = []
        for row in rows:
            try:
                pid = int(row["component_product_id"] if hasattr(row, "keys") else row[0])
                qty = float(row["cantidad"] if hasattr(row, "keys") else row[1] or 0)
            except Exception:
                continue
            if pid > 0 and qty > 0:
                comps.append((pid, qty))
        return comps

    def _virtual_from_recipe_deductions(self, product_id: int, qty: float, branch_id: int) -> Dict[int, float]:
        recipe_id = self._active_recipe_id(product_id)
        if not recipe_id:
            return {}
        comps = self._recipe_components(recipe_id)
        merged: Dict[int, float] = {}
        for component_pid, component_qty in comps:
            need = float(component_qty or 0) * qty
            exp = self.resolver.resolve_for_sale(int(component_pid), need, branch_id)
            if exp.cycle_detected:
                raise ValueError(f"RECETA_CICLICA: producto={product_id}")
            for d in exp.deductions:
                merged[d.product_id] = merged.get(d.product_id, 0.0) + d.quantity
        return merged

    def _virtual_from_recipe_availability(self, product_id: int, branch_id: int) -> float:
        recipe_id = self._active_recipe_id(product_id)
        if not recipe_id:
            return 0.0
        comps = self._recipe_components(recipe_id)
        if not comps:
            return 0.0
        mins = []
        for component_pid, component_qty in comps:
            qty = float(component_qty or 0)
            if qty <= 0:
                continue
            avail = self.avail.virtual_stock(int(component_pid), branch_id)
            mins.append(avail / qty if qty > 0 else 0.0)
        return min(mins) if mins else 0.0
