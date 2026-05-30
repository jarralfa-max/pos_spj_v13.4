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

    def _product_row(self, product_id: int):
        """Read only product columns guaranteed by the current schema.

        Do not reference optional columns such as unidad_medida/unidad_venta in
        SQL. SQLite raises `no such column` even inside COALESCE when a column is
        absent, which would block checkout before the real stock validation.
        """
        return self.db.execute(
            """
            SELECT
                id,
                nombre,
                unidad,
                tipo_producto,
                COALESCE(es_compuesto,0) AS es_compuesto,
                COALESCE(es_subproducto,0) AS es_subproducto
            FROM productos
            WHERE id=?
            LIMIT 1
            """,
            (int(product_id),),
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
            available = float(self.avail.physical_stock(int(pid), int(branch_id)) or 0)
            if available + 1e-9 < qty:
                nombre, unidad = self._product_name_unit(int(pid))
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
