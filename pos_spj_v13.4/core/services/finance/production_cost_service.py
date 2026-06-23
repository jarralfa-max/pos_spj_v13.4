# core/services/finance/production_cost_service.py — FASE 6
"""
ProductionCostService — reads production_cost_ledger after a batch closes and:
  1. Returns a ProductionCostSummary (raw_material_cost, finished_goods_cost,
     waste_cost, per-product breakdowns) for use by ProductionFinanceHandler.
  2. Updates costo_promedio in `productos` and `inventory_stock` for each
     non-waste output product using the cost_per_kg computed by CostAllocator.

This service is read/write but never called inside a SAVEPOINT — it runs from
ProductionFinanceHandler which subscribes to PRODUCCION_COMPLETADA (post-commit,
async, priority=45).  All DB writes here are therefore safe to commit directly.

Raises ValueError when the batch_id is not found.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("spj.services.finance.production_cost")


# ── Value objects ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OutputCostLine:
    """Cost attribution for a single output product in a production batch."""
    product_id:  int
    cost_total:  float   # total cost allocated to this product
    cost_per_kg: float   # cost per kg (= cost_total / weight)
    weight:      float   # kg produced
    is_waste:    bool


@dataclass
class ProductionCostSummary:
    """
    Aggregated cost data for one closed production batch.

    raw_material_cost   — source_cost_total from production_batches (what was
                          consumed from raw material stock).
    finished_goods_cost — sum of cost_total for non-waste outputs (what enters
                          finished-goods inventory).
    waste_cost          — sum of cost_total for waste outputs (expensed directly).
    output_costs        — per-product breakdown list.
    source_product_id   — product_id of the raw material input.
    branch_id           — branch that ran the production.
    """
    batch_id:            str
    raw_material_cost:   float
    finished_goods_cost: float
    waste_cost:          float
    output_costs:        List[OutputCostLine] = field(default_factory=list)
    source_product_id:   int  = 0
    branch_id:           int  = 1


# ── Service ───────────────────────────────────────────────────────────────────

class ProductionCostService:
    """
    Stateless reader of production cost data.  Instantiate once per event.

    Usage::

        svc     = ProductionCostService(db)
        summary = svc.compute_batch_costs(batch_id)
        updated = svc.update_average_costs(batch_id)
    """

    def __init__(self, db):
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────────

    def compute_batch_costs(self, batch_id: str) -> ProductionCostSummary:
        """
        Return cost summary for the batch.

        Queries:
          production_batches       → raw_material_cost, source_product_id, branch_id
          production_cost_ledger   → per-product cost_total, cost_per_kg, weight
          production_outputs       → is_waste flag per output

        Raises ValueError when the batch is not found.
        """
        batch = self._db.execute(
            "SELECT source_cost_total, source_weight, product_source_id, branch_id "
            "FROM production_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()

        if not batch:
            raise ValueError(f"production batch not found: {batch_id!r}")

        batch = dict(batch)
        raw_cost          = float(batch.get("source_cost_total") or 0)
        source_product_id = str(batch.get("product_source_id") or "")
        branch_id         = str(batch.get("branch_id") or "")

        rows = self._db.execute(
            """
            SELECT cl.product_id,
                   cl.cost_total,
                   cl.cost_per_kg,
                   cl.weight,
                   COALESCE(po.is_waste, 0) AS is_waste
            FROM   production_cost_ledger cl
            LEFT   JOIN production_outputs po ON po.id = cl.output_id
            WHERE  cl.batch_id = ?
            ORDER  BY cl.id
            """,
            (batch_id,),
        ).fetchall()

        output_costs: List[OutputCostLine] = []
        for r in rows:
            r = dict(r)
            output_costs.append(OutputCostLine(
                product_id  = int(r["product_id"]),
                cost_total  = float(r["cost_total"]),
                cost_per_kg = float(r["cost_per_kg"]),
                weight      = float(r["weight"]),
                is_waste    = bool(r["is_waste"]),
            ))

        finished_cost = sum(l.cost_total for l in output_costs if not l.is_waste)
        waste_cost    = sum(l.cost_total for l in output_costs if     l.is_waste)

        return ProductionCostSummary(
            batch_id            = batch_id,
            raw_material_cost   = raw_cost,
            finished_goods_cost = round(finished_cost, 4),
            waste_cost          = round(waste_cost, 4),
            output_costs        = output_costs,
            source_product_id   = source_product_id,
            branch_id           = branch_id,
        )

    def update_average_costs(self, batch_id: str) -> int:
        """
        Update costo_promedio / costo for each non-waste output product using
        cost_per_kg from production_cost_ledger.

        Updates two tables:
          productos.costo              — canonical unit cost column
          inventory_stock.costo_promedio — per-branch average cost cache

        Skips waste products (their cost is expensed, not inventoried).
        Returns the number of products updated.
        """
        rows = self._db.execute(
            """
            SELECT cl.product_id,
                   cl.cost_per_kg,
                   COALESCE(po.is_waste, 0) AS is_waste
            FROM   production_cost_ledger cl
            LEFT   JOIN production_outputs po ON po.id = cl.output_id
            WHERE  cl.batch_id = ? AND cl.cost_per_kg > 0
            """,
            (batch_id,),
        ).fetchall()

        updated = 0
        for r in rows:
            r = dict(r)
            if r["is_waste"]:
                continue

            product_id  = int(r["product_id"])
            cost_per_kg = round(float(r["cost_per_kg"]), 4)

            self._db.execute(
                "UPDATE productos SET costo = ? WHERE id = ?",
                (cost_per_kg, product_id),
            )
            self._db.execute(
                "UPDATE inventory_stock SET costo_promedio = ? "
                "WHERE product_id = ?",
                (cost_per_kg, product_id),
            )
            updated += 1

        logger.debug(
            "update_average_costs: batch=%s updated=%d products",
            batch_id, updated,
        )
        return updated

    def allocate_recipe_run_costs(
        self,
        conn,
        produccion_id: int,
        sucursal_id: int,
        recipe_type: str,
        movimientos: list[dict],
        componentes_db: list[dict],
        base_product_id: int,
    ) -> dict:
        """
        Costing for RecipeEngine path (single-step production).
        Creates/uses production_cost_ledger rows and updates product/inventory costs once.
        """
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS production_cost_ledger ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, output_id TEXT, "
                "product_id INTEGER, weight REAL, pct_utilizable REAL DEFAULT 0, "
                "cost_total REAL, cost_per_kg REAL, operation_id TEXT, "
                "sucursal_id INTEGER, usuario TEXT, base_product_id INTEGER, is_waste INTEGER DEFAULT 0)"
            )
        except Exception:
            pass

        raw = conn.execute("SELECT COALESCE(precio_compra,0) FROM productos WHERE id=?", (base_product_id,)).fetchone()
        raw_cpk = float(raw[0] if raw else 0.0)
        raw_qty = sum(abs(float(m["delta"])) for m in movimientos if float(m.get("delta", 0)) < 0 and m.get("movement_type") != "MERMA_PRODUCCION")
        raw_cost = round(raw_cpk * raw_qty, 4)

        outputs = [m for m in movimientos if float(m.get("delta", 0)) > 0 and m.get("movement_type") == "PRODUCCION_ENTRADA"]
        waste = [m for m in movimientos if m.get("movement_type") == "MERMA_PRODUCCION"]
        waste_qty = sum(abs(float(m["delta"])) for m in waste)
        finished_qty = sum(float(m["delta"]) for m in outputs)
        total_basis = finished_qty + waste_qty
        if total_basis <= 0:
            return {"raw_material_cost": raw_cost, "finished_goods_cost": 0.0, "waste_cost": 0.0}

        waste_mode = "absorb"
        try:
            r = conn.execute("SELECT valor FROM configuraciones WHERE clave='production_waste_mode' LIMIT 1").fetchone()
            if r and str(r[0]).strip().lower() in ("separate", "separado", "expense"):
                waste_mode = "separate"
        except Exception:
            pass

        waste_cost = 0.0 if waste_mode == "absorb" else round(raw_cost * (waste_qty / total_basis), 4)
        finished_pool = round(raw_cost - waste_cost, 4)

        factor_map = {str(c.get("product_id") or c.get("component_product_id") or ""): float(c.get("factor_costo") or 1.0) for c in componentes_db}
        basis = []
        for o in outputs:
            pid = int(o["product_id"]); q = float(o["delta"]); factor = factor_map.get(pid, 1.0)
            basis.append((pid, q, max(0.0001, q * factor)))
        basis_total = sum(b for _, _, b in basis) or 1.0
        finished_cost = 0.0
        for pid, q, b in basis:
            alloc = round(finished_pool * (b / basis_total), 4)
            cpk = round(alloc / q, 4) if q > 0 else 0.0
            finished_cost += alloc
            conn.execute("INSERT INTO production_cost_ledger(batch_id, output_id, product_id, weight, pct_utilizable, cost_total, cost_per_kg) VALUES (?,?,?,?,?,?,?)",
                         (str(produccion_id), f"P{produccion_id}_{pid}", pid, q, 100.0, alloc, cpk))
            conn.execute("UPDATE productos SET precio_compra=? WHERE id=?", (cpk, pid))
            conn.execute("UPDATE productos SET costo=? WHERE id=?", (cpk, pid))
            conn.execute("INSERT OR IGNORE INTO inventory_stock(product_id,branch_id,quantity,costo_promedio) VALUES (?,?,0,?)", (pid, sucursal_id, cpk))
            conn.execute("UPDATE inventory_stock SET costo_promedio=? WHERE product_id=? AND branch_id=?", (cpk, pid, sucursal_id))
        if waste_cost > 0 and waste_qty > 0:
            conn.execute(
                "INSERT INTO production_cost_ledger(batch_id, output_id, product_id, weight, pct_utilizable, cost_total, cost_per_kg, is_waste) VALUES (?,?,?,?,?,?,?,1)",
                (str(produccion_id), f"P{produccion_id}_WASTE", base_product_id, waste_qty, 0.0, waste_cost, round(waste_cost / waste_qty, 4)),
            )
        return {
            "raw_material_cost": round(raw_cost, 4),
            "finished_goods_cost": round(finished_cost, 4),
            "waste_cost": round(waste_cost, 4),
        }
