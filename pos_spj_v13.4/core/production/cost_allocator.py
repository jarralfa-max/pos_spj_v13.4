
# core/production/cost_allocator.py
# ── CostAllocator — Distribución de Costos de Producción ─────────────────────
#
# Aplica la distribución de costos calculada por YieldCalculator a la DB,
# actualizando production_cost_ledger y el costo_promedio de cada producto
# en inventario_actual.

from __future__ import annotations
import logging
from typing import List

from core.production.yield_calculator import CostAllocation, OutputYield

logger = logging.getLogger("spj.production.cost_allocator")


class CostAllocator:

    def __init__(self, conn):
        self.conn = conn

    def persist_allocations(
        self,
        batch_id: str,
        allocations: List[CostAllocation],
        output_id_map: dict,          # product_id → output.id
    ) -> None:
        """
        Inserta registros en production_cost_ledger.
        output_id_map: {product_id: output_row_id} para el FK.
        """
        for a in allocations:
            oid = output_id_map.get(a.product_id, "")
            self.conn.execute("""
                INSERT INTO production_cost_ledger
                    (batch_id, output_id, product_id, weight,
                     pct_utilizable, cost_total, cost_per_kg)
                VALUES (?,?,?,?,?,?,?)
            """, (batch_id, oid, a.product_id, a.weight,
                  a.pct_utilizable, a.cost_total, a.cost_per_kg))
        logger.debug("cost_ledger: %d asignaciones para batch %s", len(allocations), batch_id)

    def update_product_average_cost(
        self, product_id: int, new_cost_per_kg: float
    ) -> None:
        """
        Actualiza el costo promedio en productos (columna costo).
        Solo actualiza si el nuevo costo es mayor a 0.
        """
        if new_cost_per_kg <= 0:
            return
        self.conn.execute(
            "UPDATE productos SET costo = ? WHERE id = ?",
            (round(new_cost_per_kg, 4), product_id)
        )

    def get_batch_cost_summary(self, batch_id: str) -> dict:
        """Resumen de costos de un lote."""
        row = self.conn.execute("""
            SELECT
                SUM(cost_total)     AS total_asignado,
                COUNT(*)            AS productos,
                MIN(cost_per_kg)    AS min_costo_kg,
                MAX(cost_per_kg)    AS max_costo_kg,
                AVG(cost_per_kg)    AS avg_costo_kg
            FROM production_cost_ledger
            WHERE batch_id = ?
        """, (batch_id,)).fetchone()
        return dict(row) if row else {}

    def get_product_allocation(self, batch_id: str, product_id: int) -> dict | None:
        row = self.conn.execute("""
        SELECT * FROM production_cost_ledger
            WHERE batch_id=? AND product_id=?
        """, (batch_id, product_id)).fetchone()
        return dict(row) if row else None
